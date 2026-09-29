"""Words, the way names and questions are compared: prose and code identifiers alike.

    words("Who approves a £300 refund?")    -> ["who", "approves", "a", "300", "refund"]
    words("needs_approval")                  -> ["needs", "approval"]
    words("needsApproval")                   -> ["needs", "approval"]
    words("NeedsApproval")                   -> ["needs", "approval"]
    words("APPROVAL_THRESHOLD_GBP")          -> ["approval", "threshold", "gbp"]
    words("parseHTTPResponse")               -> ["parse", "http", "response"]
    words("api-base"), words("orders.service.cancel_order")  split on - and . too
    words("sha256Hash"), words("v2Handler")  -> ["sha256", "hash"], ["v2", "handler"]

snake_case, SCREAMING_SNAKE, camelCase, PascalCase, kebab-case and dotted paths
all come apart at the same seams, so "needs approval", needs_approval and
needsApproval name the same thing. A run of capitals is one word (HTTP, ID),
ending where a capitalised word begins (HTTPServer -> http, server). Digits
stay with the letters before them. Prose is unchanged: it has no seams inside
its words.
"""
import re

CHUNK = re.compile(r"[^\W_]+")  # letters and digits; _ - . / space and the rest are seams


def _camel(chunk: str) -> list:
    """camelCase and PascalCase apart, in any alphabet: a boundary before a capital
    that follows a small letter or a digit (needsApproval, id2FA), and before the
    last capital of a run when a small letter follows it (HTTPServer, XMLHttp)."""
    parts, start = [], 0
    for i in range(1, len(chunk)):
        prev, c = chunk[i - 1], chunk[i]
        nxt = chunk[i + 1] if i + 1 < len(chunk) else ""
        if c.isupper() and (prev.islower() or prev.isdigit() or (prev.isupper() and nxt.islower())):
            parts.append(chunk[start:i])
            start = i
    return parts + [chunk[start:]]


def split_identifier(name: str) -> list:
    """The words in one name or identifier, lower case, in order."""
    return [part.lower() for chunk in CHUNK.findall(name) for part in _camel(chunk)]


def words(text: str) -> list:
    """Lower-cased words of a question, a name or an identifier. Names and questions
    are split the same way, so either can be written in any style."""
    return split_identifier(text)
