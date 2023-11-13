import re

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from TexSoup import TexNode
from TexSoup.utils import Token

from pyconduit.models.latex import LatexDocument, LatexObject, LatexText
from pyconduit.shared.helpers import get_config
from pyconduit.shared.latex.core import (
    CaptionMacro,
    ErrorCommand,
    FootnoteMacro,
    GlobalConfig,
    IncludeGraphics,
    ItemExtractor,
    LabelMacro,
    MetadataNode,
    ProblemMacro,
    RefMacro,
    SetIteratorMacro,
    TextCommand,
    TextEnv,
    WrapfigureEnv,
    convert_latex,
)
from pyconduit.shared.latex.markdown_centerline import centerline_plugin
from pyconduit.shared.latex.markdown_stars import star_only_emphasis

cfg = get_config("latex")
locale = get_config("localization")
md_generator = MarkdownIt("gfm-like")
# Unfortunately, underscores trigger emphasis plugin, and latex formulas can include underscores.
# That means I actually have to write my own emphasis plugin. Damn.
md_generator.disable("emphasis")
md_generator.use(anchors_plugin, max_level=3, permalink=True)
md_generator.use(centerline_plugin)
md_generator.use(star_only_emphasis)

# These are applied before TexSoup is invoked
Replacements = {
    "{\\it": "\\textit{",
    "{\\bf": "\\textbf{",
    "<<": "&laquo;",
    ">>": "&raquo;",
    "----": "—",
    "---": "—",
    "--": "–",
    "\\\\": "\n\n",
    "\\ ": " ",
    "~": " ",
}

text_regex = re.compile(r"\\text\{(.+?)}")
comment_regex = re.compile(r"(^|[^\\])%.*?\n", re.M)

# These are applied during the latex compilation
BuiltinCommands = {
    # visual changes
    "it": ErrorCommand("textit"),
    "bf": ErrorCommand("textbf"),
    "HUGE": TextCommand("# #1", 1),
    "Huge": TextCommand("# #1", 1),
    "huge": TextCommand("## #1", 1),
    "LARGE": TextCommand("## #1", 1),
    "Large": TextCommand("### #1", 1),
    "large": TextCommand("### #1", 1),
    "textit": TextCommand("*#1*", 1, trim_contents=True, empty_contents=""),
    "textbf": TextCommand("**#1**", 1, trim_contents=True, empty_contents=""),
    "texttt": TextCommand("`#1`", 1, trim_contents=True, empty_contents=""),
    "sout": TextCommand("~~#1~~", 1, trim_contents=True, empty_contents=""),
    "ldots": TextCommand("...", 0),
    # problem macros
    # TIL we use \z instead of \ze
    "z": ProblemMacro(problem=1, letter=-1, fmt="%(z)i%(ext)s.", conduit_include=False, start=True),
    "zp": ProblemMacro(problem=1, letter=0, fmt="%(z)i%(ext)s.", cfmt="%(z)i", standalone=True),
    "zpstar": ProblemMacro(problem=1, letter=0, fmt="%(z)i*%(ext)s.", cfmt="%(z)i*", standalone=True),
    "zcirc": ProblemMacro(problem=1, letter=0, fmt="%(z)i$^\\circ$%(ext)s.", cfmt="%(z)i<sup>o</sup>", standalone=True),
    "zpcirc": ProblemMacro(
        problem=1, letter=0, fmt="%(z)i$^\\circ$%(ext)s.", cfmt="%(z)i<sup>o</sup>", standalone=True
    ),
    "leth": ProblemMacro(letter=1, fmt="%(leth)s%(ext)s)", cfmt="%(z)i%(leth)s", inline=True),
    "lett": ProblemMacro(letter=1, fmt="%(leth)s%(ext)s)", cfmt="%(z)i%(leth)s"),
    "lettstar": ProblemMacro(letter=1, fmt="%(leth)s*%(ext)s)", cfmt="%(z)i%(leth)s*"),
    "lethcirc": ProblemMacro(letter=1, fmt="%(leth)s$^\\circ$%(ext)s)", cfmt="%(z)i%(leth)s<sup>o</sup>", inline=True),
    "lettcirc": ProblemMacro(letter=1, fmt="%(leth)s$^\\circ$%(ext)s)", cfmt="%(z)i%(leth)s<sup>o</sup>"),
    "zncirc": ProblemMacro(
        problem=1, letter=0, fmt="%(z)i.%(leth)s$^\\circ$%(ext)s)", cfmt="%(z)i%(leth)s<sup>o</sup>", start=True
    ),
    "zn": ProblemMacro(problem=1, letter=0, fmt="%(z)i.%(leth)s%(ext)s)", cfmt="%(z)i%(leth)s", start=True),
    "zecirc": ProblemMacro(problem=1, letter=-1, fmt="%(z)i$^\\circ$%(ext)s.", conduit_include=False, start=True),
    "ze": ProblemMacro(problem=1, letter=-1, fmt="%(z)i%(ext)s.", conduit_include=False, start=True),
    # global configuration
    "sheetid": GlobalConfig("sheet_id"),
    "sheetname": GlobalConfig("sheet_name"),
    "cdtexport": GlobalConfig("conduit-strategy"),
    "letterord": GlobalConfig("letter-order"),
    # environments
    "center": TextEnv("-> #1 <-"),
    "centerline": TextCommand("-> #1 <-", 1),
    "tikzpicture": TextEnv("#1", "tikz"),
    "wrapfigure": WrapfigureEnv(),
    "itemize": ItemExtractor("* %(item)s"),
    # miscellanous
    "bigskip": TextCommand("", 0),
    "medskip": TextCommand("\n\n", 0),
    "vspace": TextCommand("", 1),
    "vspace*": TextCommand("", 1),
    "hspace": TextCommand("", 1),
    "hspace*": TextCommand("", 1),
    "noindent": TextCommand("", 0),
    "newpage": TextCommand("", 0),
    "qquad": TextCommand("    ", 0),
    "quad": TextCommand("    ", 0),
    "mbox": TextCommand("\\text{{#1}}", 1),
    "fbox": TextCommand("\\text{{#1}}", 1),
    # complex commands
    "label": LabelMacro(),
    "ref": RefMacro(),
    "setiterator": SetIteratorMacro(),
    "includegraphics": IncludeGraphics(),
    "caption": CaptionMacro(),
    "footnote": FootnoteMacro(),
}


def collect_excess(doc: LatexDocument, current_metadata: MetadataNode) -> None:
    for i in range(cfg["compilation"]["excess-stacking"]):
        new_node, excess_text = current_metadata.collect(None)
        if new_node:
            doc.objects.append(LatexObject.parse_obj(new_node))
            current_metadata = MetadataNode("text")
            if excess_text:
                new_node, _ = current_metadata.collect(excess_text)
        else:
            break
    else:
        raise ValueError(locale["exceptions"]["stacking_limit"])


def build_latex(latext: str) -> LatexDocument:
    doc = LatexDocument(objects=[], orig_doc=latext)
    for value, replacement in Replacements.items():
        latext = latext.replace(value, replacement)

    latext = comment_regex.sub("\\1", latext)
    soup, context = convert_latex(dict(BuiltinCommands), latext)

    if sheet_id := context.get("sheet_id"):
        doc.sheet_id = sheet_id
    else:
        raise ValueError(locale["exceptions"]["no_sheet_id"])
    if sheet_name := context.get("sheet_name"):
        doc.sheet_name = sheet_name
    else:
        raise ValueError(locale["exceptions"]["no_sheet_name"])

    doc.conduit_strategy = context.get("conduit-strategy", "none").lower()

    current_metadata = MetadataNode("text")
    for node in soup.contents:
        is_math = isinstance(node, TexNode) and node.name and node.name[0] == "$"
        if isinstance(node, str) or isinstance(node, Token) or is_math:
            node = str(node)
            if not is_math:
                node = text_regex.sub("\\1", node)
            new_node, excess_text = current_metadata.collect(node)
            if new_node:
                # excess_text is guaranteed None because the current mode does not collect text
                doc.objects.append(LatexObject.parse_obj(new_node))
                current_metadata = MetadataNode("text")
        elif isinstance(node, MetadataNode):
            collect_excess(doc, current_metadata)
            current_metadata = node
        elif (isinstance(node, TexNode) and node.contents == [""]) or node is None:
            pass
        else:
            raise ValueError(locale["exceptions"]["unknown_node"] % dict(node=node, type=type(node)))

    collect_excess(doc, current_metadata)

    # Now we need to postprocess the document to split anything including linebreaks into parts.
    # Cringe, I know.
    new_objects = []
    for latex_part in doc.objects:
        if not hasattr(latex_part, "text"):
            new_objects.append(latex_part)
            continue

        text = latex_part.text.split("<br />")  # noqa
        latex_part.text = text[0]
        new_objects.append(latex_part)
        for more_text in text[1:]:
            new_objects.append(LatexText(text=more_text))

    doc.objects = new_objects
    return doc


def generate_html(doc: LatexDocument) -> str:
    md = doc.generate_markdown().replace("-> ###", "### ->").replace("\\{", "\\\\{").replace("\\}", "\\\\}")
    return md_generator.render(md)
