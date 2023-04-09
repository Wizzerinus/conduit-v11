# Process only *this*
from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.rules_inline.emphasis import tokenize as tokenize_emp


def tokenize(state: StateInline, silent: bool):
    marker = state.srcCharCode[state.pos]
    if marker == 0x5F:
        return False

    return tokenize_emp(state, silent)


def _postProcess(state, delimiters):
    # Blatant copy from markdown_it code.
    # I have no idea how this parser works, but the copy seems to be good enough for my usecase.
    i = len(delimiters) - 1
    while i >= 0:
        startDelim = delimiters[i]

        # /* * */
        if startDelim.marker != 0x2A:
            i -= 1
            continue

        # Process only opening markers
        if startDelim.end == -1:
            i -= 1
            continue

        endDelim = delimiters[startDelim.end]

        # If the previous delimiter has the same marker and is adjacent to this one,
        # merge those into one strong delimiter.
        #
        # `<em><em>whatever</em></em>` -> `<strong>whatever</strong>`
        #
        isStrong = (
            i > 0
            and delimiters[i - 1].end == startDelim.end + 1
            and delimiters[i - 1].token == startDelim.token - 1
            and delimiters[startDelim.end + 1].token == endDelim.token + 1
            and delimiters[i - 1].marker == startDelim.marker
        )

        ch = chr(startDelim.marker)

        token = state.tokens[startDelim.token]
        token.type = "strong_open" if isStrong else "em_open"
        token.tag = "strong" if isStrong else "em"
        token.nesting = 1
        token.markup = ch + ch if isStrong else ch
        token.content = ""

        token = state.tokens[endDelim.token]
        token.type = "strong_close" if isStrong else "em_close"
        token.tag = "strong" if isStrong else "em"
        token.nesting = -1
        token.markup = ch + ch if isStrong else ch
        token.content = ""

        if isStrong:
            state.tokens[delimiters[i - 1].token].content = ""
            state.tokens[delimiters[startDelim.end + 1].token].content = ""
            i -= 1

        i -= 1


def postProcess(state: StateInline):
    """Walk through delimiter list and replace text tokens with tags."""
    _postProcess(state, state.delimiters)

    for token in state.tokens_meta:
        if token and "delimiters" in token:
            _postProcess(state, token["delimiters"])


def star_only_emphasis(md: MarkdownIt):
    md.inline.ruler.after("strikethrough", "emphasis", tokenize)
    md.inline.ruler2.after("strikethrough", "emphasis", postProcess)
