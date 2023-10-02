import logging
from abc import abstractmethod
from typing import Protocol, runtime_checkable

from pyconduit.models.bundle import BundleDocument
from pyconduit.models.conduit import Conduit, ConduitContent
from pyconduit.models.user import UserUnprivileged
from pyconduit.shared.datastore import datastore_manager, deatomize
from pyconduit.shared.formulas import execute_formula
from pyconduit.shared.helpers import get_config

locale = get_config("localization")
accounts = datastore_manager.get("accounts")
logger = logging.getLogger("pyconduit.website.conduit")


@runtime_checkable
class SupportsContains(Protocol):
    """An ABC with one abstract method __index__."""

    __slots__ = ()

    @abstractmethod
    def __contains__(self, item: str) -> bool:
        pass


def calculate_with_formula(
    conduit: Conduit, file_id: str, filename: str, users: list[UserUnprivileged], formula: str
) -> ConduitContent:
    conduit_document = ConduitContent(
        id=file_id,
        conduit=dict(conduit.dict()),
        users=users,
        name=filename,
        real_indices=list(range(len(conduit.problem_names))),
    )
    try:
        data, answer = execute_formula(conduit_document, formula)
        if "Error" in answer or "Exception" in answer:
            logger.warning(answer)
            conduit_document.formula_error = answer
        else:
            conduit_document = ConduitContent.parse_obj(data)
            real_indices = []
            for problem in conduit_document.conduit.problem_names:
                try:
                    real_indices.append(conduit.problem_names.index(problem))
                except ValueError:
                    real_indices.append(-1)
            conduit_document.real_indices = real_indices
    except RuntimeError as e:
        logger.warning("Failed to execute formula for '%s': %s", file_id, e)
        conduit_document.formula_error = str(e)
    return conduit_document


def get_all_users(conduit: Conduit) -> list[UserUnprivileged]:
    users = {
        login: UserUnprivileged.parse_obj(deatomize(account))
        for login, account in accounts.accounts.items()
        if account["privileges"]["conduit_generation"]
    }

    for login in conduit.content.keys():
        if login not in users:
            if login in accounts.accounts:
                username = accounts.accounts[login].name
            else:
                username = login
            users[login] = UserUnprivileged(login=login, name=username)

    return sorted(users.values(), key=lambda user: user.name)


def postprocess_limited_conduit(
    user_logins: SupportsContains, bundle_document: BundleDocument
) -> tuple[list, list, list]:
    problems = []
    styles = []
    row_styles = [""]
    precomputed = bundle_document.precomputed
    conduit = precomputed.conduit

    first_column = [locale["pages"]["sheet_viewer"]["mode_conduit"]]
    for user_data in precomputed.users:
        row_id = user_data.login
        if not (row_id.startswith("_") and row_id in precomputed.limited_rows) and row_id not in user_logins:
            continue
        first_column.append(user_data.name)
        row_styles.append(precomputed.row_styles[row_id])
    problems.append(first_column)
    styles.append([])

    for index, problem in enumerate(conduit.problem_names):
        if precomputed.real_indices[index] == -1 and problem not in precomputed.limited_columns:
            continue

        prob_append, style_append = [problem], [""]
        for user_data in precomputed.users:
            row_id = user_data.login
            if not (row_id.startswith("_") and row_id in precomputed.limited_rows) and row_id not in user_logins:
                continue
            prob_append.append(conduit.content[row_id][index])
            style_append.append(precomputed.styles.get(row_id, {}).get(problem, ""))
        problems.append(prob_append)
        styles.append(style_append)
    return problems, styles, row_styles
