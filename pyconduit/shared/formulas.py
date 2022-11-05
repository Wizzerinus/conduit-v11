import logging
import multiprocessing
import resource
from typing import Callable, TypeVar

import _queue
from asteval import Interpreter
from coloraide import Color
from coloraide.interpolate import Interpolator

from pyconduit.models.conduit import ConduitContent
from pyconduit.models.user import UserSensitive

formula_lock = multiprocessing.Lock()
Position = int | None
# (position to insert into, row/column id, row/column name, list of values) -> value in the new cell
ConduitCallback = Callable[[Position, str | int, str, list[str]], str]
# (row id, column caption text, cell value) -> style
FormatterCallback = Callable[[str, str, str], None | str]
Range = tuple[str, str]
ColorTuple = tuple[int, int, int]
T = TypeVar("T")
logger = logging.getLogger("pyconduit.shared.formulas")
# Experimentally figured the least amount of memory needed is 30M, but setting it higher
# because server can be loaded differently in different requests
# Also, numbers near 70 often cause ASGI errors for no reason so should avoid these
MEMORY_LIMIT = 1024 * 1024 * 150


def insert_into(values: list[T], value: T, position: Position):
    if position is None:
        values.append(value)
    else:
        values.insert(position, value)


def read_queue(queue: multiprocessing.Queue) -> str:
    if "provider" in globals():
        raise RuntimeError("Don't try to execute inside the sandbox")
    while True:
        try:
            yield queue.get_nowait()
        except _queue.Empty:
            break


class FormulaProvider:
    def __init__(self, doc: ConduitContent):
        self.doc = doc
        self.usernames = {user.login: user.name for user in doc.users}
        self.problem_names = list(doc.conduit.problem_names)
        self.problem_name_set = set(self.problem_names)

    @staticmethod
    def base_value(value: str) -> str:
        return value.split(";", 1)[0]

    @staticmethod
    def is_solved(value: str) -> bool:
        value = FormulaProvider.base_value(value)
        return value != "" and value != "0"

    def is_real(self, row_id: str, column_id: str) -> bool:
        return row_id[0] != "_" and column_id in self.problem_name_set

    def add_column(self, position: Position, name: str, callback: ConduitCallback):
        insert_into(self.doc.conduit.problem_names, name, position)
        for user, row in self.doc.conduit.content.items():
            value = str(callback(position, user, self.usernames.get(user, user), list(row)))
            insert_into(row, value, position)

    def add_row(self, position: Position, row_id: str, row_name: str, callback: ConduitCallback):
        row_id = f"_{row_id}"
        insert_into(self.doc.users, UserSensitive(login=row_id, name=row_name), position)
        self.usernames[row_id] = row_name
        values = []
        for index, problem in enumerate(self.doc.conduit.problem_names):
            value = str(
                callback(
                    position, index, problem, [self.doc.conduit.content[x][index] for x in self.doc.conduit.content]
                )
            )
            values.append(value)
        self.doc.conduit.content[row_id] = values

    def add_formatter(self, callback: FormatterCallback):
        for index, problem in enumerate(self.doc.conduit.problem_names):
            for user in self.doc.conduit.content:
                value = self.doc.conduit.content[user][index]
                style = callback(user, problem, value)
                if style is not None:
                    self.doc.styles.setdefault(user, {})[problem] = style

    def add_gradient_formatter(
        self,
        rg: Range,
        from_color: ColorTuple,
        to_color: ColorTuple,
        mid_color: ColorTuple = None,
        min_value_override: int = None,
        max_value_override: int = None,
        mid_value_override: int = None,
    ):
        if rg[0] not in ("column", "row"):
            raise ValueError("Invalid range: first argument has to be 'column' or 'row'")

        if rg[0] == "column":
            problem_index = self.doc.conduit.problem_names.index(rg[1])
            values = [self.doc.conduit.content[user][problem_index] for user in self.doc.conduit.content]
        else:
            values = self.doc.conduit.content[rg[1]]

        values_ints = []
        for i in values:
            try:
                values_ints.append(int(self.base_value(i)))
            except ValueError:
                values_ints.append(0)

        min_value = min(values_ints) if min_value_override is None else min_value_override
        max_value = max(values_ints) if max_value_override is None else max_value_override
        mid_value = (min_value + max_value) // 2 if mid_value_override is None else mid_value_override

        if min_value >= max_value:
            color_str = f"rgb{from_color}"
            colors = [color_str for _ in values_ints]
        else:
            interpolations = [Color(f"rgb{from_color}"), Color(f"rgb{to_color}")]
            if mid_color is not None:
                interpolations.insert(1, Color(f"rgb{mid_color}"))
            inter = Color.interpolate(interpolations)

            values_recalc = []
            for i in values_ints:
                if i < min_value:
                    values_recalc.append(0)
                elif i > max_value:
                    values_recalc.append(1)
                elif i < mid_value:
                    values_recalc.append(1/2 * (i - min_value) / (mid_value - min_value))
                else:
                    values_recalc.append(1/2 * (i - mid_value) / (max_value - mid_value) + 1 / 2)

            colors = [inter(i).to_string() for i in values_recalc]

        if rg[0] == "column":
            for user, color in zip(self.doc.conduit.content, colors):
                self.doc.styles.setdefault(user, {})[rg[1]] = f"background-color: {color}"
        else:
            for problem, color in zip(self.doc.conduit.problem_names, colors):
                self.doc.styles.setdefault(rg[1], {})[problem] = f"background-color: {color}"


def run_formula(aev: Interpreter, formula: str, return_dict: dict[str, str]):
    aev(formula)
    return_dict["value"] = aev.symtable["provider"].doc.dict()


class Interstream:
    def __init__(self):
        self.__data = multiprocessing.Queue()

    def write(self, data):
        self.__data.put(data)

    def flush(self):
        pass

    def get(self):
        answer = read_queue(self.__data)
        return "".join(answer)


def execute_formula(doc: ConduitContent, formula: str) -> tuple[dict, str]:
    fp = FormulaProvider(doc)
    stream = Interstream()
    aev = Interpreter(
        usersyms={"provider": fp, "is_solved": fp.is_solved, "is_real": fp.is_real, "sheet_id": doc.id},
        builtins_readonly=True,
        writer=stream,
        err_writer=stream,
        no_assert=True,
        no_delete=True,
        no_raise=True,
        no_print=True,
    )

    with formula_lock:
        with multiprocessing.Manager() as mgr:
            # cannot safely do it because ASGI crashes
            current_limits = resource.getrlimit(resource.RLIMIT_AS)
            limit_value = min(current_limits[0], MEMORY_LIMIT) if current_limits[0] != -1 else MEMORY_LIMIT
            data = mgr.dict()
            proc = multiprocessing.Process(target=run_formula, args=(aev, formula, data))
            try:
                resource.setrlimit(resource.RLIMIT_AS, (limit_value, current_limits[1]))
                proc.start()
                proc.join(0.5)

                answer = stream.get()
                result_value = data.get("value", {})

                if proc.exitcode:
                    proc.terminate()
                    raise RuntimeError("Formula execution crashed")
                if proc.is_alive():
                    proc.terminate()
                    proc.join()
                    raise RuntimeError("Formula execution timed out")
            finally:
                proc.terminate()
                resource.setrlimit(resource.RLIMIT_AS, current_limits)

    return result_value, answer
