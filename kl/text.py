"""Bytes to text, and the fingerprints deduplication compares.

Text is what quotes are checked against, so it is kept close to the bytes:
decoded (UTF-8, else Latin-1), the byte-order mark dropped, line endings made
\\n and trailing spaces cut. Two files that differ only in those ways are the
same text. HTML loses its tags. Formats that need a parser (PDF, Word) are
refused unless the caller sends their text.

Near duplicates are found with MinHash over five-word shingles: 128 minimum
hashes estimate the Jaccard similarity of two documents' shingle sets.
"""
import hashlib
import html
import re

TEXT_TYPES = {".md", ".markdown", ".txt", ".text", ".csv", ".json", ".yaml", ".yml", ".eml", ".log", ".rst",
              ".html", ".htm", ".xml", ".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".toml", ".ini", ""}
NEEDS_PARSER = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".rtf", ".odt"}
SHINGLE = 5
HASHES = 128
_MASK = (1 << 64) - 1
_SEEDS = [int.from_bytes(hashlib.sha256(f"kl-minhash-{i}".encode()).digest()[:8], "big") | 1 for i in range(HASHES)]


class Unsupported(ValueError):
    pass


def suffix(name: str) -> str:
    m = re.search(r"(\.[A-Za-z0-9]+)$", name or "")
    return m.group(1).lower() if m else ""


def normalise(data: bytes, name: str = "") -> str:
    ext = suffix(name)
    if ext in NEEDS_PARSER:
        raise Unsupported(f"{ext} files need their text sent with them (send text=..., or convert first)")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if ext in (".html", ".htm"):
        text = re.sub(r"(?is)<(script|style).*?</\1>", "", text)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def shingles(text: str) -> set:
    words = re.findall(r"\w+", text.lower())
    if len(words) < SHINGLE:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


def minhash(text: str) -> list:
    hashed = [int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big") for s in shingles(text)]
    if not hashed:
        return [0] * HASHES
    return [min(((h ^ seed) * 0x9E3779B97F4A7C15) & _MASK for h in hashed) for seed in _SEEDS]


def similarity(a: list, b: list) -> float:
    if not a or not b:
        return 0.0
    return sum(x == y for x, y in zip(a, b)) / HASHES
