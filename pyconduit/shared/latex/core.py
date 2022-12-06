import abc
import re

from TexSoup import TexNode, TexSoup
from TexSoup.data import TexCmd, TexText

from pyconduit.shared.datastore import datastore_manager
from pyconduit.shared.helpers import get_config

cfg = get_config("latex")
locale = get_config("localization")
first_problem_character = cfg["iterators"]["first-letter"]
problem_skips = cfg["iterators"]["letter-skips"]
problem_skip_indices = [ord(c) - ord(first_problem_character) for c in problem_skips]
priority_cap = 10000
Punctuation = ".,;:!?()[]{}"
image_datastore = datastore_manager.get("images")


class MetadataNode:
    def __init__(self, cls: str, collect_text: bool = True, **kwargs):
        self.collect_text = collect_text
        self.kwargs = kwargs
        kwargs["cls"] = cls

    def collect(self, text: str | None) -> tuple[None | dict, str]:
        if self.collect_text and "text" not in self.kwargs:
            self.kwargs["text"] = ""

        if self.collect_text and text is not None:
            if text and text[0] not in Punctuation:
                self.kwargs["text"] += " "
            self.kwargs["text"] += text.strip()
        elif not self.collect_text or self.kwargs["text"].strip():
            excess_text = ""
            if self.collect_text:
                # self.kwargs["text"] = self.kwargs["text"].strip()
                if "\n\n" in self.kwargs["text"]:
                    self.kwargs["text"], excess_text = self.kwargs["text"].split("\n\n", 1)
                    # excess_text = excess_text.strip("\n\r\t")
            return self.kwargs, excess_text

        return None, ""


apply_result = str | TexNode | MetadataNode


class LatexCommand(abc.ABC):
    priority = 0

    def set_priority(self, prio: int):
        self.priority = prio
        return self

    @abc.abstractmethod
    def apply(self, context: dict, node: TexNode, *args: str) -> apply_result | tuple[apply_result] | bool:
        pass

    def invoke(self, context: dict, node: TexNode, *args: str) -> None:
        replacement = self.apply(context, node, *args)
        if replacement is False:
            return

        for arg in node.parent.args:
            if node in arg.children:
                contents = []
                for c in arg.contents:
                    if c != node:
                        contents.append(c)
                    elif isinstance(replacement, tuple):
                        contents.extend(replacement)
                    else:
                        contents.append(replacement)

                # we need to do this because TexSoup has a sanity check, but we're using a stronger syntax than LaTeX
                arg._contents = [TexText(c) if isinstance(c, str) else c for c in contents]
                break
        else:
            if isinstance(replacement, tuple):
                node.parent.replace(node, *replacement)
            else:
                node.parent.replace(node, replacement)

    def get_priority(self) -> int:
        return self.priority

    def recursion_ready(self, cmd: TexNode, all_commands: dict[str, "LatexCommand"]) -> bool:
        return True


class TextCommand(LatexCommand):
    hash_regex = re.compile(r"(^|[^\\])#([0-9])")

    def __init__(
        self,
        content: str,
        num_args: int,
        optional_arg: str = None,
        trim_contents: bool = False,
        empty_contents: str = None,
    ):
        self.content = self.hash_regex.sub(lambda t: f"{t[1]}{{{int(t[2]) - 1}}}", content)
        self.num_args = num_args
        self.optional_arg = optional_arg
        self.trim_contents = trim_contents
        self.empty_contents = empty_contents

    def apply(self, context: dict, node: TexNode, *args: str):
        if (
            len(args) > self.num_args
            or len(args) < self.num_args - 1
            or (len(args) == self.num_args - 1 and self.optional_arg is None)
        ):
            raise ValueError(
                locale["exceptions"]["invalid_argcount"]
                % dict(expected=self.num_args, actual=len(args), name=node.name)
            )

        if len(args) == self.num_args:
            args = list(args)
        else:
            args = [self.optional_arg] + list(args)

        if self.trim_contents:
            args = [str(a).strip() for a in args]

        if self.empty_contents is not None and not [arg for arg in args if arg]:
            return self.empty_contents
        return self.content.format(*args)

    def recursion_ready(self, cmd: TexNode, all_commands: dict[str, LatexCommand]) -> bool:
        arg_data = [x if arg.contents else "" for arg in cmd.args for x in arg.contents]
        return not any(isinstance(c, TexCmd) and c.name in all_commands for c in arg_data)


class ItemExtractor(LatexCommand):
    def __init__(self, fmt: str):
        self.fmt = fmt

    def apply(self, context: dict, node: TexNode, *args: str):
        ans = []
        for child in node.contents:
            if not child:
                continue

            if isinstance(child, TexNode) and child.name == "item":
                ans.append(str(child)[6:])
            elif len(ans) == 0:
                raise ValueError(locale["exceptions"]["itemextract_error"] % dict(name=child))
            else:
                ans[-1] += str(child)
        node.expr.contents = []
        items = [self.fmt % dict(index=index, item=item) for index, item in enumerate(ans)]
        return MetadataNode("text", text="\n\n" + "\n".join(items)), MetadataNode("text")

    def recursion_ready(self, cmd: TexNode, all_commands: dict[str, LatexCommand]) -> bool:
        return not any(isinstance(c, TexNode) and c.name in all_commands for c in cmd.contents)


class TextEnv(TextCommand):
    def __init__(self, content: str, metaname: str = "text", optional_arg: str = None, trim_contents: bool = False):
        super().__init__(content, 0, optional_arg, trim_contents)
        self.metaname = metaname

    def apply(self, context: dict, node: TexNode, *args: str):
        return (
            MetadataNode(self.metaname),
            self.content.format("".join(str(c) for c in node.contents if c not in args)),
            MetadataNode("text"),
        )

    def get_priority(self) -> int:
        return -1


class WrapfigureEnv(TextCommand):
    def __init__(self):
        super().__init__("", 0, None, False)
        self.metaname = "text"

    def apply(self, context: dict, node: TexNode, *args: str):
        ans = [MetadataNode("text")]
        for child in node.contents:
            if child not in args:
                ans.append(child)
        ans.append(MetadataNode("text"))
        return tuple(ans)

    def get_priority(self) -> int:
        return -357


class ErrorCommand(LatexCommand):
    def __init__(self, repl_name: str):
        self.replace_name = repl_name

    def apply(self, context: dict, node: TexNode, *args: str):
        raise ValueError(locale["exceptions"]["command_banned"] % dict(name=node.name, instead=self.replace_name))


class GlobalConfig(LatexCommand):
    def __init__(self, target_name: str, strip: bool = True):
        self.target_name = target_name
        self.strip = strip

    def apply(self, context: dict, node: TexNode, *args: str):
        context[self.target_name] = args[0]
        if self.strip:
            context[self.target_name] = context[self.target_name].strip()
        return ""


class ProblemMacro(LatexCommand):
    def __init__(
        self,
        fmt: str,
        letter: int | None = None,
        problem: int | None = None,
        conduit_include: bool = True,
        standalone: bool = False,
        start: bool = False,
        inline: bool = False,
        cfmt: str = "",
    ):
        self.fmt = fmt
        self.letter = letter
        self.problem = problem
        self.conduit_include = conduit_include
        self.cfmt = cfmt
        self.newline_after = standalone
        self.newline_before = standalone or start
        self.inline = inline

    @staticmethod
    def update_iterator(context: dict, it_name: str, value: int):
        if value is None:
            return

        if value > 0:
            context["iterators"][it_name] += value
        else:
            context["iterators"][it_name] = value

    def apply(self, context: dict, node: TexNode, *args: str):
        self.update_iterator(context, "problem", self.problem)
        self.update_iterator(context, "letter", self.letter)
        letter_index = context["iterators"]["letter"] + sum(
            1 for i in problem_skip_indices if i < context["iterators"]["letter"]
        )
        letter_str = chr(ord(first_problem_character) + letter_index)
        format_data = {"z": context["iterators"]["problem"], "leth": letter_str}

        if not args:
            extra_text = ""
        elif isinstance(args[0], str):
            extra_text = f" ({args[0]})"
        else:
            extra_text = f" ({args[0].contents[0]})"  # type: ignore
        format_data["ext"] = extra_text
        fmt, cfmt = self.fmt % format_data, self.cfmt % format_data
        fmt = fmt.replace("))", ")")
        context["last_iterator"] = (cfmt or fmt).rstrip(").")
        return MetadataNode(
            "problem",
            num=fmt,
            conduit_include=self.conduit_include,
            conduit_num=cfmt,
            nlb=self.newline_before,
            nla=self.newline_after,
            inline=self.inline,
        )

    def get_priority(self) -> int:
        return -333


class LabelMacro(LatexCommand):
    def get_priority(self) -> int:
        return -333

    def apply(self, context: dict, node: TexNode, *args: str):
        if len(args) != 1:
            raise ValueError(locale["exceptions"]["invalid_env_argcount"])
        if not context.get("last_iterator"):
            raise ValueError(locale["exceptions"]["label_no_problem"] % dict(label=args[0]))

        context["labels"][args[0]] = context["last_iterator"]
        return ""


class RefMacro(LatexCommand):
    def get_priority(self) -> int:
        return -333

    def apply(self, context: dict, node: TexNode, *args: str):
        if len(args) != 1:
            raise ValueError(locale["exceptions"]["invalid_env_argcount"])
        if args[0] not in context["labels"]:
            context["need_regen"] = True
            return False

        return f'**{context["labels"][args[0]]}**'


class IncludeGraphics(LatexCommand):
    def apply(self, context: dict, node: TexNode, *args: str):
        if len(args) < 1:
            raise ValueError(locale["exceptions"]["invalid_graphics_argcount"])

        filename = args[-1].split("/")[-1].split(".")[0]
        if filename not in image_datastore.images:
            raise ValueError(locale["exceptions"]["invalid_graphics_filename"] % dict(filename=filename))

        return MetadataNode("image", filename=filename, collect_text=False)


class CaptionMacro(LatexCommand):
    def apply(self, context: dict, node: TexNode, *args: str):
        if len(args) != 1:
            raise ValueError(
                locale["exceptions"]["invalid_argcount"] % dict(name="caption", expected=1, actual=len(args))
            )

        context["iterators"]["captions"] += 1
        context["last_iterator"] = context["iterators"]["captions"]
        return args[0]

    def get_priority(self):
        return -3


def soup_to_command(cmd: TexNode) -> tuple[str, LatexCommand]:
    brace_args = [arg for arg in cmd.args if arg.name == "BraceGroup"]
    bracket_args = [arg for arg in cmd.args if arg.name == "BracketGroup"]
    if len(brace_args) != 2 or len(bracket_args) > 2:
        raise ValueError(locale["exceptions"]["malformed_newcommand"] % dict(actual=cmd.name))

    num_args = 0 if len(bracket_args) == 0 else int(bracket_args[0].contents[0])
    optional_arg = None if len(bracket_args) <= 1 else bracket_args[1].contents[0]
    name = str(brace_args[0].contents[0]).lstrip("\\")
    return name, TextCommand(
        str(brace_args[1].contents[0]).replace("{", "{{").replace("}", "}}"), num_args, optional_arg
    )


def convert_latex(context_commands: dict[str, LatexCommand], latext: str) -> tuple[TexSoup, dict]:
    soup = TexSoup(latext)
    command_adds = (
        list(soup.find_all("newcommand"))
        + list(soup.find_all("renewcommand"))
        + list(soup.find_all("newcommand*"))
        + list(soup.find_all("renewcommand*"))
    )
    for new_command in command_adds:
        name, command = soup_to_command(new_command)
        context_commands[name] = command
        new_command.parent.remove(new_command)
    latext = str(soup)

    char_limit = cfg["compilation"]["character-limit"]
    nesting_limit = cfg["compilation"]["command-nesting-limit"]
    max_regens = 2
    context = {
        "iterators": {"problem": 0, "letter": 0, "captions": 0},
        "commands": context_commands,
        "labels": {},
    }

    for j in range(max_regens):
        soup = TexSoup(latext)
        all_priorities = sorted(set(c.get_priority() for c in context_commands.values()), reverse=True)
        for i in range(nesting_limit):
            last_stage = priority_cap
            for priority in all_priorities:
                command_keys = list(
                    c for c in context_commands.keys() if context_commands[c].get_priority() == priority
                )
                for cmd in soup.find_all(command_keys):
                    callback = context_commands[cmd.name]
                    if not callback.recursion_ready(cmd, context_commands):
                        continue

                    arg_data = [" ".join(str(x) for x in arg.contents) if arg.contents else "" for arg in cmd.args]
                    callback.invoke(context, cmd, *arg_data)
                    last_stage = priority
                    soup_len = len(str(soup))
                    if soup_len > char_limit:
                        raise ValueError(locale["exceptions"]["latex_big"] % dict(limit=char_limit, size=soup_len))
                if last_stage == priority:
                    break
            if last_stage == priority_cap:
                break
        else:
            raise ValueError(locale["exceptions"]["nesting_limit"] % dict(limit=nesting_limit))

        if not context.get("need_regen"):
            return soup, context
    raise ValueError(locale["exceptions"]["regen_limit"] % dict(limit=max_regens))
