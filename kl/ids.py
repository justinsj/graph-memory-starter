"""Ids, hashes and time: every id is a prefix and random letters; every time is UTC ISO text."""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def new(prefix: str, n: int = 14) -> str:
    return f"{prefix}_" + "".join(secrets.choice(ALPHABET) for _ in range(n))


def token(prefix: str) -> str:
    """A secret to hand out once and keep only as its hash."""
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def sha256(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def claim_id(entity_id: str, kind: str, text: str, amount, unit, valid_from, valid_to) -> str:
    """A claim's content id: the same fact, from any source, in any build, has the same id."""
    key = json.dumps([entity_id, kind, " ".join(text.split()).lower(), amount, unit, valid_from, valid_to])
    return "clm_" + sha256(key)[:24]


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


class Clock:
    """Now, as the service sees it. Tests move it forward instead of sleeping.

    Today is the date in the service's time zone (KL_TIMEZONE, UTC by default), or
    GRAPH_MEMORY_TODAY when that is set, as recall reads it."""

    def __init__(self, tz: str = "UTC"):
        self.offset = 0.0
        self.tz = tz

    def now(self) -> datetime:
        from datetime import timedelta
        return datetime.now(timezone.utc) + timedelta(seconds=self.offset)

    def stamp(self) -> str:
        return iso(self.now())

    def epoch(self) -> float:
        return self.now().timestamp()

    def today(self):
        import os
        from datetime import date, timedelta
        from zoneinfo import ZoneInfo
        pinned = os.environ.get("GRAPH_MEMORY_TODAY")
        if pinned:
            return date.fromisoformat(pinned) + timedelta(seconds=self.offset)
        return self.now().astimezone(ZoneInfo(self.tz)).date()

    def advance(self, seconds: float) -> None:
        self.offset += seconds
