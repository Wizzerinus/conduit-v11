from typing import List

from markdown_it import MarkdownIt
from markdown_it.token import Token


def centerline_plugin(md: MarkdownIt):
    def centering(state):
        tokens: List[Token] = state.tokens
        for i, token in enumerate(tokens):
            if is_centerline(token):
                tokens[parent_token(tokens, i)].attrSet("class", "text-center")
                token.content = token.content[3:-3]

    md.core.ruler.after("block", "centerline", centering)

    def parent_token(tokens, index):
        target_level = tokens[index].level - 1
        for i in range(1, index + 1):
            if tokens[index - i].level == target_level:
                return index - i
        return -1

    def is_centerline(token: Token):
        return token.type == "inline" and token.content.startswith("-> ") and token.content.endswith(" <-")
