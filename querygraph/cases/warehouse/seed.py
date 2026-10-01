"""Two warehouses, Leeds and Manchester, from a stock count on 24 August 2026 to 17:00 on
30 September: receipts, put-aways, replenishments, shipments, damage and returns for four
products, the nightly snapshot, and the reservations behind the orders. Then 30 September
at Leeds for the blue mug, move by move, with the rows each rule in questions.json needs.

Deterministic: the same rows on every build.
"""
import random
from collections import defaultdict
from datetime import datetime, timedelta

NOW = datetime(2026, 9, 30, 17, 0)
PRODUCTS = [("MUG-BLU", "Blue enamel mug", 6, 450), ("MUG-GRN", "Green enamel mug", 6, 450),
            ("PLT-WHT", "White dinner plate", 12, 320), ("BWL-SND", "Sand stoneware bowl", 8, 380)]
PER_CASE = {sku: n for sku, _, n, _ in PRODUCTS}
LOCATIONS = [(1, "LDS", "LDS/DOCK", "dock"), (2, "LDS", "LDS/BULK-A", "bulk"), (3, "LDS", "LDS/BULK-B", "bulk"),
             (4, "LDS", "LDS/PICK-01", "pick"), (5, "LDS", "LDS/PICK-02", "pick"),
             (6, "LDS", "LDS/QUARANTINE", "quarantine"), (7, "LDS", "LDS/RETURNS", "returns"),
             (8, "LDS", "LDS/TRANSIT-IN", "transit"),
             (11, "MAN", "MAN/DOCK", "dock"), (12, "MAN", "MAN/BULK", "bulk"), (13, "MAN", "MAN/PICK", "pick"),
             (14, "MAN", "MAN/QUARANTINE", "quarantine"), (15, "MAN", "MAN/RETURNS", "returns")]
SITES = {"LDS": {"dock": 1, "quarantine": 6, "returns": 7}, "MAN": {"dock": 11, "quarantine": 14, "returns": 15}}


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def at(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


def shelves(warehouse, sku):
    """The bulk and pick locations a product lives in."""
    if warehouse == "MAN":
        return 12, 13
    return (2, 4) if sku.startswith("MUG") else (3, 5)


class Stock:

    def __init__(self):
        self.moves, self.reservations = [], []
        self.units = defaultdict(int)  # (sku, location) -> units, done moves only
        self.seq = defaultdict(lambda: 1000)

    def ref(self, prefix):
        self.seq[prefix] += 1
        return f"{prefix}{self.seq[prefix]}"

    def move(self, sku, src, dst, qty, uom, when, ref, state="done"):
        units = qty * (PER_CASE[sku] if uom == "case" else 1)
        if state == "done" and src:
            assert self.units[(sku, src)] >= units, (sku, src, when, ref)
            self.units[(sku, src)] -= units
        if state == "done" and dst:
            self.units[(sku, dst)] += units
        self.moves.append((len(self.moves) + 1, sku, src, dst, qty, uom, state, ts(when), ref))

    def reserve(self, order_ref, sku, warehouse, qty, created, expires, released=None):
        self.reservations.append((len(self.reservations) + 1, order_ref, sku, warehouse, qty, ts(created),
                                  ts(expires), ts(released) if released else None))


def background(s, rng):
    """Each product at each warehouse, a day at a time."""
    returns = []  # (inspect_at, warehouse, sku, qty)
    for wh in SITES:
        for sku in PER_CASE:
            bulk, pick = shelves(wh, sku)
            s.move(sku, None, bulk, rng.randint(20, 40), "case", at("2026-08-24 06:00"), "COUNT/2026-08-24")
            s.move(sku, None, pick, rng.randint(20, 60), "unit", at("2026-08-24 06:00"), "COUNT/2026-08-24")
    day = datetime(2026, 8, 24)
    while day <= datetime(2026, 9, 30):
        for wh, site in SITES.items():
            for sku in PER_CASE:
                if wh == "LDS" and sku == "MUG-BLU" and day.date() == NOW.date():
                    continue  # traps() writes this day by hand
                bulk, pick = shelves(wh, sku)
                events = [(day + timedelta(hours=7), "replenish", 0)]
                if day.weekday() in (0, 3):
                    events.append((day + timedelta(hours=8, minutes=rng.randint(0, 59)), "receipt", rng.randint(8, 20)))
                for _ in range(rng.randint(3, 10)):
                    events.append((day + timedelta(minutes=rng.randint(360, 1200)), "ship", rng.randint(1, 3)))
                if rng.random() < 0.05:
                    events.append((day + timedelta(minutes=rng.randint(480, 1080)), "damage", rng.randint(1, 2)))
                if rng.random() < 0.2:
                    events.append((day + timedelta(minutes=rng.randint(480, 1080)), "return", rng.randint(1, 2)))
                for when, kind, qty in sorted(events):
                    if when > NOW:
                        continue
                    if kind == "replenish" and s.units[(sku, pick)] < 30 and s.units[(sku, bulk)] > 0:
                        s.move(sku, bulk, pick, min(48, s.units[(sku, bulk)]), "unit", when, s.ref("INT/REP/"))
                    elif kind == "receipt":
                        s.move(sku, None, site["dock"], qty, "case", when, s.ref("PO-"))
                        putaway = when + timedelta(minutes=rng.randint(60, 180))
                        if putaway <= NOW:
                            s.move(sku, site["dock"], bulk, qty, "case", putaway, s.ref("INT/PUT/"))
                    elif kind == "ship" and s.units[(sku, pick)] >= qty:
                        s.move(sku, pick, None, qty, "unit", when, s.ref("SO-8"))
                    elif kind == "damage" and s.units[(sku, pick)] >= qty:
                        s.move(sku, pick, site["quarantine"], qty, "unit", when, s.ref("INT/DMG/"))
                    elif kind == "return":
                        s.move(sku, None, site["returns"], qty, "unit", when, s.ref("RET/"))
                        returns.append((day + timedelta(days=1, hours=10), wh, sku, qty, rng.random() < 0.7))
        for inspect_at, wh, sku, qty, good in [r for r in returns if r[0].date() == day.date()]:
            if inspect_at <= NOW and not (wh == "LDS" and sku == "MUG-BLU" and day.date() == NOW.date()):
                dst = shelves(wh, sku)[1] if good else SITES[wh]["quarantine"]
                s.move(sku, SITES[wh]["returns"], dst, qty, "unit", inspect_at, s.ref("INT/RET/"))
        day += timedelta(days=1)


def traps(s):
    """Leeds, 30 September, the blue mug, after the 02:00 snapshot."""
    sku = "MUG-BLU"

    def ship(hhmm, qty):
        s.move(sku, 4, None, qty, "unit", at(f"2026-09-30 {hhmm}"), s.ref("SO-8"))

    # ledger-not-snapshot: every move below happened after the 02:00 snapshot
    ship("08:05", 2)
    # cases: 15 cases arrive, 90 mugs
    s.move(sku, None, 1, 15, "case", at("2026-09-30 08:40"), "PO-1187")
    ship("09:10", 3)
    # sellable: 10 cases put away, 5 still on the dock; done-only: the second scan of the same pallet, cancelled
    s.move(sku, 1, 2, 10, "case", at("2026-09-30 10:15"), "INT/PUT/3301")
    s.move(sku, 1, 3, 10, "case", at("2026-09-30 10:16"), "INT/PUT/3302", state="cancelled")
    s.move(sku, 2, 4, 36, "unit", at("2026-09-30 11:00"), "INT/REP/2201")
    ship("11:30", 4)
    # sellable: a customer's return waits for inspection; two mugs chipped on the pick face
    s.move(sku, None, 7, 3, "unit", at("2026-09-30 12:05"), "RET/2231")
    ship("13:00", 1)
    s.move(sku, 4, 6, 2, "unit", at("2026-09-30 14:20"), "INT/DMG/0412")
    ship("14:45", 2)
    # sellable: 8 cases left Manchester at 15:00; they reach the Leeds dock tomorrow
    s.move(sku, 12, 8, 8, "case", at("2026-09-30 15:00"), "INT/TRF/0077")
    s.move(sku, 8, 1, 8, "case", at("2026-10-01 09:00"), "INT/TRF/0077", state="planned")
    ship("15:30", 3)
    ship("16:30", 2)
    # live-reservations: paid orders waiting to ship, one of them booked on the 17:30 wave
    for order, qty, hhmm in [("SO-90412", 2, "09:30"), ("SO-90418", 1, "11:10"), ("SO-90425", 4, "14:05"),
                             ("SO-90431", 1, "15:20"), ("SO-90440", 2, "16:50")]:
        s.reserve(order, sku, "LDS", qty, at(f"2026-09-30 {hhmm}"), at(f"2026-10-07 {hhmm}"))
    s.move(sku, 4, None, 2, "unit", at("2026-09-30 17:30"), "SO-90412", state="planned")
    # live-reservations: checkouts hold stock for 15 minutes; two ran out, one is still open
    s.reserve("CART-6d0e", sku, "LDS", 3, at("2026-09-30 15:40"), at("2026-09-30 15:55"))
    s.reserve("CART-7f3a", sku, "LDS", 2, at("2026-09-30 16:20"), at("2026-09-30 16:35"))
    s.reserve("CART-81bc", sku, "LDS", 1, at("2026-09-30 16:52"), at("2026-09-30 17:07"))
    # wholesale-ring-fenced: a café chain's weekly call-off, allocated from the two cases Leeds holds back
    s.reserve("WS-5521", sku, "LDS", 6, at("2026-09-29 14:00"), at("2026-10-13 14:00"))
    # released: an order cancelled this morning; and one waiting at Manchester, not Leeds
    s.reserve("SO-90399", sku, "LDS", 2, at("2026-09-30 08:00"), at("2026-10-07 08:00"), released=at("2026-09-30 10:30"))
    s.reserve("SO-90433", sku, "MAN", 3, at("2026-09-30 15:05"), at("2026-10-07 15:05"))


def reservations_for_shipments(s, rng):
    """Every order shipped since 28 September was reserved first, and released when it shipped."""
    for _, sku, src, dst, qty, _, state, moved_at, ref in list(s.moves):
        when = datetime.strptime(moved_at, "%Y-%m-%d %H:%M:%S")
        if dst is None and state == "done" and ref.startswith("SO-8") and when >= at("2026-09-28 00:00"):
            wh = "MAN" if src > 10 else "LDS"
            created = when - timedelta(minutes=rng.randint(60, 1200))
            s.reserve(ref, sku, wh, qty, created, created + timedelta(days=7), released=when)


def snapshots(s):
    rows = []
    for d in range(25, 31):
        taken = datetime(2026, 9, d, 2, 0)
        units = defaultdict(int)
        for _, sku, src, dst, qty, uom, state, moved_at, _ in s.moves:
            if state == "done" and moved_at < ts(taken):
                n = qty * (PER_CASE[sku] if uom == "case" else 1)
                if src:
                    units[(sku, src)] -= n
                if dst:
                    units[(sku, dst)] += n
        rows += [(ts(taken), sku, loc, n) for (sku, loc), n in sorted(units.items()) if n]
    return rows


def rows():
    s = Stock()
    rng = random.Random(20260930)
    background(s, rng)
    traps(s)
    reservations_for_shipments(s, rng)
    return {"products": PRODUCTS, "locations": LOCATIONS, "stock_moves": s.moves,
            "stock_snapshot": snapshots(s), "reservations": s.reservations}
