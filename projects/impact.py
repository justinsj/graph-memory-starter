"""A project's thesis, projected impact, estimated effort and priority, worked out from its numbers.

A thesis says: if <change>, <outcome> will <fall | rise | improve> by potentially
<amount> <unit>. The amount is never written by hand. It is the product of the
numbers the thesis names (its formula), each of which was found in a document,
answered by a named person, or estimated by a named person, and says which. Until
every number is in, the amount is "still being researched", never a guess.

Estimated effort is in person-days. Priority is projected impact per person-day.
Projects are compared only when their impact is in the same unit, unless the
workspace gives a value per unit (a staff hour is worth £45), which puts them all
in money.
"""
import math
import re

DIRECTIONS = {"reduce": "fall", "increase": "rise", "improve": "improve"}
NUMBER_STATUSES = ("needed", "asked", "found", "answered", "estimated")
KNOWN = ("found", "answered", "estimated")


WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
         "fifty": 50, "hundred": 100, "dozen": 12, "half": 0.5, "once": 1, "twice": 2}
FIGURE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?")


def figures(text: str) -> set:
    """The numbers a sentence states: "1,240", "6.5", "30%", "four times", "twice"."""
    t = str(text).lower()
    out = {float(m.group(1).replace(",", "") + (m.group(2) or "")) for m in FIGURE.finditer(t)}
    return out | {float(v) for w, v in WORDS.items() if re.search(rf"\b{w}\b", t)}


def mentions(value, text: str) -> bool:
    """True when the sentence states this number, so the number can be pointed at."""
    return any(abs(float(value) - f) < 1e-9 for f in figures(text))


def fmt(x) -> str:
    if x is None:
        return "?"
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    return f"{x:,.1f}"


def numbers_of(rec) -> dict:
    return {n["key"]: n for n in rec.get("numbers") or []}


def percent(unit) -> bool:
    return str(unit or "").strip().lower() in ("%", "percent", "per cent")


def terms(th, nums) -> list:
    """One (key, label, value or None, unit, status) per formula item: a number's key, or a constant."""
    out = []
    for item in th["formula"]:
        if isinstance(item, dict):
            out.append((None, item.get("label") or "", float(item["value"]), item.get("unit") or "", "constant"))
            continue
        n = nums.get(item)
        if not n:
            out.append((item, item, None, "", "undefined"))
            continue
        known = n["status"] in KNOWN and n.get("value") is not None
        out.append((item, n.get("label") or item, n["value"] if known else None, n.get("unit") or "", n["status"]))
    return out


def evaluate(rec, unit_values: dict = None, currency: str = "GBP") -> dict:
    """Everything the figures say about one record. Pure: the record is not changed."""
    th = rec.get("thesis")
    nums = numbers_of(rec)
    effort = (rec.get("effort") or {}).get("days")
    out = {"thesis": None, "complete": False, "value": None, "unit": None, "direction": None, "working": None,
           "reach": None, "missing": [], "estimated": [], "numbers": list(nums.values()),
           "effort_days": effort, "effort": rec.get("effort"), "per_day": None, "money": None,
           "money_per_day": None, "currency": currency}
    if not th:
        return out
    parts = terms(th, nums)
    missing = [k for k, _, v, _, _ in parts if v is None]
    value = None
    if not missing:
        value = math.prod(v / 100 if percent(u) else v for _, _, v, u, _ in parts)
    verb = DIRECTIONS.get(th["direction"], th["direction"])
    amount = f"by potentially {fmt(value)} {th['unit']}" if value is not None else         f"by an amount still being researched ({len(parts) - len(missing)} of {len(parts)} numbers in)"
    reach = nums.get(th.get("reach")) if th.get("reach") else None
    across = f", across {fmt(reach['value'])} {reach['unit']}"         if reach and reach.get("value") is not None and reach["status"] in KNOWN else ""
    def term(lb, v, u, st):
        if v is None:
            return f"[{lb}]"
        shown = f"{fmt(v)}%" if percent(u) else f"{fmt(v)} {u}".strip()
        return shown + (" (estimated)" if st == "estimated" else "")
    working = " × ".join(term(lb, v, u, st) for _, lb, v, u, st in parts)
    out.update(thesis=f"If {th['change']}, {th['outcome']} will {verb} {amount}{across}.", complete=value is not None,
               value=value, unit=th["unit"], direction=th["direction"], missing=missing,
               working=working + (f" = {fmt(value)} {th['unit']}" if value is not None else ""),
               reach={k: reach.get(k) for k in ("key", "label", "value", "unit", "status")} if reach else None,
               estimated=[k for k, _, _, _, st in parts if st == "estimated"])
    if value is not None and effort:
        out["per_day"] = value / effort
    rate = (unit_values or {}).get(th["unit"])
    if value is not None and rate is not None:
        out["money"] = value * rate
        if effort:
            out["money_per_day"] = out["money"] / effort
    return out


def rank(items: list) -> dict:
    """items: [(project id, evaluation)]. Returns {"ranked": [...], "by_unit": {...}, "unranked": [...]}.

    Ranked in one list by money per person-day when every complete project has a
    money value; otherwise within each unit by impact per person-day. A project
    missing numbers or an effort is unranked, with the reason."""
    ready = [(pid, e) for pid, e in items if e["complete"] and e["effort_days"]]
    unranked = [(pid, e, "no thesis yet" if not e["thesis"] else
                 f"numbers still being researched: {', '.join(e['missing'])}" if not e["complete"] else
                 "no estimated effort yet") for pid, e in items if (pid, e) not in ready]
    if ready and all(e["money_per_day"] is not None for _, e in ready):
        ranked = sorted(ready, key=lambda x: -x[1]["money_per_day"])
        return {"basis": "money per person-day", "ranked": ranked, "by_unit": {}, "unranked": unranked}
    by_unit = {}
    for pid, e in ready:
        by_unit.setdefault(e["unit"], []).append((pid, e))
    for unit in by_unit:
        by_unit[unit].sort(key=lambda x: -x[1]["per_day"])
    return {"basis": "impact per person-day, within each unit", "ranked": [], "by_unit": by_unit, "unranked": unranked}
