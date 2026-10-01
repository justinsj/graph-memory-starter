"""Kettle & Kiln's sales ledger, 1 January to 14 September 2026 (the extract was taken early on
15 September): ordinary trade through the web shop, the till and the phone desk, then the rows
each evidence set in evidence.json needs, each marked with the finding it is there for.

Deterministic: the same rows on every build.
"""
import random
from datetime import date, datetime, timedelta

NOW = datetime(2026, 9, 15, 5, 0)  # UTC: when the extract was taken
FIRST_DAY, LAST_DAY = date(2026, 1, 1), date(2026, 9, 14)  # London days
BST = (datetime(2026, 3, 29, 1, 0), datetime(2026, 10, 25, 1, 0))  # UTC instants: the clocks go forward, then back
STAFF_DOMAIN = "kettleandkiln.example"
TRAINING_EMAIL = "training@till.local"
AMENDING_FROM = date(2026, 7, 6)  # the phone desk's back-office tool: it writes lines, never the header
AMENDED = {"jul-aug": 23, "sep": 5}  # amended orders, by when they were placed
OUTLIER_DAY = date(2026, 8, 14)  # one trade order makes it the best day
SALE_DAY = date(2026, 8, 29)  # the bank holiday weekend sale: the best day for retail
AFTER_MIDNIGHT = {date(2026, 6, 30): 3, date(2026, 8, 31): 6}  # web orders just after midnight London: the next day's

CATALOGUE = [  # (category, name, retail price in pence, how often it is picked)
    ("mugs", "Enamel mug, blue", 1400, 9), ("mugs", "Enamel mug, sand", 1400, 7), ("mugs", "Stoneware mug, moss", 1600, 8),
    ("mugs", "Stoneware mug, charcoal", 1600, 6), ("mugs", "Espresso cup", 1150, 4),
    ("bowls", "Cereal bowl, blue", 1500, 6), ("bowls", "Cereal bowl, sand", 1500, 5), ("bowls", "Pasta bowl", 2200, 5),
    ("bowls", "Serving bowl", 3400, 3),
    ("plates", "Side plate", 1350, 6), ("plates", "Dinner plate", 1900, 6), ("plates", "Platter", 3800, 2),
    ("jugs", "Milk jug", 2800, 3), ("jugs", "Teapot", 4800, 2),
    ("linen", "Tea towel", 950, 7), ("linen", "Napkin set of four", 2400, 3), ("linen", "Linen tablecloth", 6800, 1),
    ("candles", "Tin candle", 1450, 5), ("candles", "Pillar candle", 2600, 3),
]
FIRST = ["Olivia", "Amelia", "Isla", "Ava", "Mia", "Ivy", "Lily", "Freya", "Noah", "Oliver", "George", "Leo", "Arthur",
         "Harry", "Jack", "Thomas", "Oscar", "Sophie", "Grace", "Ella", "Priya", "Tom", "Ruth", "Aisha", "Daniel", "Hannah"]
LAST = ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies", "Patel", "Wright", "Walker",
        "Evans", "Khan", "Hughes", "Green", "Hall", "Clarke", "Lewis", "Murphy", "Byrne", "Ahmed", "Price"]
MAIL = ["gmail.com", "outlook.com", "icloud.com", "yahoo.co.uk", "proton.me", "btinternet.com", "hotmail.com"]
TRADE = ["Sea Salt Interiors", "The Larder Cafe", "Wren & Co Gifts", "Mill House B&B", "Harbourside Deli",
         "Fern Studio", "The Old Bakery", "Coastline Holiday Lets", "North Street Kitchen", "Bramble Florist"]
STAFF = ["Megan Cole", "Sam Okafor", "Lucy Fenn", "Ravi Shah", "Ellie Burke", "Joe Marsh"]

WEEKDAY = [28, 28, 30, 32, 38, 52, 42]  # ordinary orders a day, Monday to Sunday
SEASON = {1: .8, 2: .8, 3: .9, 4: .95, 5: 1.0, 6: 1.0, 7: 1.05, 8: 1.1, 9: 1.0}
CHANNELS = [("web", 58), ("shop", 32), ("phone", 10)]
LINES = {"web": [(1, 10), (2, 36), (3, 29), (4, 15), (5, 7), (6, 3)],
         "shop": [(1, 46), (2, 30), (3, 16), (4, 8)],
         "phone": [(1, 22), (2, 38), (3, 25), (4, 15)]}
QUANTITY = [(1, 72), (2, 19), (3, 6), (4, 3)]
HOURS = {  # London hours: the web shop runs past midnight, the till and the phones keep shop hours
    "web": [(0, 3), (1, 1), (6, 1), (7, 3), (8, 4), (9, 5), (10, 5), (11, 5), (12, 6), (13, 6), (14, 5), (15, 5),
            (16, 5), (17, 5), (18, 6), (19, 8), (20, 9), (21, 9), (22, 7), (23, 5)],
    "shop": [(h, 1) for h in range(9, 18)],
    "phone": [(h, 1) for h in range(9, 17)]}


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def utc(london):
    """A London wall-clock time as UTC. Nothing is generated in the hour the clocks skip or repeat."""
    shifted = london - timedelta(hours=1)
    return shifted if BST[0] <= shifted < BST[1] else london


def pick(rng, weighted):
    return rng.choices([v for v, _ in weighted], [w for _, w in weighted])[0]


class Ledger:

    def __init__(self, rng):
        self.rng = rng
        self.customers, self.products, self.orders, self.items, self.amendments = [], [], [], [], []
        for i, (cat, name, price, _) in enumerate(CATALOGUE, 1):
            self.products.append([i, f"KK-{cat[:3].upper()}-{i:03d}", name, cat, price])
        self.weights = [w for *_, w in CATALOGUE]

    def customer(self, name, email, kind, created_at):
        self.customers.append([len(self.customers) + 1, name, email, kind, ts(created_at)])
        return len(self.customers)

    def order(self, customer_id, channel, placed_london, lines, status="completed", trade=False):
        """An order and its lines, the header written at checkout from the lines. lines: [(product, quantity)]."""
        oid = len(self.orders) + 1
        rows = []
        for product, qty in lines:
            price = self.products[product - 1][4]
            unit = round(price * 0.7) if trade else price
            rows.append([len(self.items) + len(rows) + 1, oid, product, qty, unit, qty * unit])
        self.items += rows
        self.orders.append([oid, customer_id, channel, ts(utc(placed_london)), status, len(rows),
                            sum(r[3] for r in rows), sum(r[5] for r in rows)])
        return oid

    def basket(self, channel, trade=False):
        n = self.rng.randint(3, 7) if trade else pick(self.rng, LINES[channel])
        products = self.rng.sample(range(1, len(CATALOGUE) + 1), k=n) if trade else \
            [self.rng.choices(range(1, len(CATALOGUE) + 1), self.weights)[0] for _ in range(n)]
        out = {}
        for p in products:  # a product picked twice is one line with more units
            out[p] = out.get(p, 0) + (self.rng.randint(6, 24) if trade else pick(self.rng, QUANTITY))
        return list(out.items())


def london_days():
    d = FIRST_DAY
    while d <= LAST_DAY:
        yield d
        d += timedelta(days=1)


def at(day, hour, rng):
    t = datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), rng.randint(0, 59))
    return t + timedelta(days=1) if hour == 0 else t  # hour 0: just after midnight, at the end of the day's evening


def rows():
    rng = random.Random(20260915)
    led = Ledger(rng)
    training = led.customer("Till training", TRAINING_EMAIL, "retail", datetime(2025, 3, 3))  # not sales
    staff = [led.customer(n, f"{n.split()[0].lower()}@{STAFF_DOMAIN}", "retail", datetime(2025, 4, 1)) for n in STAFF]
    trade = [led.customer(n, f"orders@{n.lower().replace(' & ', '').replace(' ', '').replace('&', '')}.example",
                          "trade", datetime(2025, 2, 1) + timedelta(days=17 * i)) for i, n in enumerate(TRADE)]
    retail = []
    for _ in range(2400):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        retail.append(led.customer(f"{first} {last}", f"{first}.{last}{rng.randint(1, 999)}@{rng.choice(MAIL)}".lower(),
                                   "retail", datetime(2024, 6, 1) + timedelta(days=rng.randint(0, 560))))
    cancelled = []
    for day in london_days():
        wd = day.weekday()
        n = max(5, round(rng.gauss(WEEKDAY[wd] * SEASON[day.month], 4)))
        if day == SALE_DAY:  # best retail day: the bank holiday weekend sale
            n = round(n * 1.6)
        for _ in range(n):
            channel = pick(rng, CHANNELS)
            if channel == "phone" and wd == 6:
                channel = "web"  # the phone desk is shut on Sundays
            hour = pick(rng, HOURS[channel])
            if wd == 6 and channel == "shop" and not 10 <= hour < 16:
                hour = rng.randint(10, 15)
            status = "cancelled" if rng.random() < 0.03 else "completed"
            oid = led.order(rng.choice(retail), channel, at(day, hour, rng), led.basket(channel), status)
            if status == "cancelled":
                cancelled.append(oid)
        for _ in range(AFTER_MIDNIGHT.get(day, 0)):  # London days: placed on the UTC day before the London one
            led.order(rng.choice(retail), "web", at(day, 0, rng), led.basket("web"))
        if rng.random() < 0.55:  # staff purchases at the till: not sales
            led.order(rng.choice(staff), "shop", at(day, rng.randint(9, 17), rng),
                      [(rng.choices(range(1, len(CATALOGUE) + 1), led.weights)[0], 1) for _ in range(rng.randint(1, 3))])
        if wd == 1:  # Tuesday morning till training: real-looking completed sales that are not sales
            for _ in range(3):
                led.order(training, "shop", at(day, 9, rng), [(rng.randint(1, len(CATALOGUE)), 1)
                                                               for _ in range(rng.randint(1, 2))])
        if wd < 5 and rng.random() < 0.3:  # trade accounts, at 70% of the retail price
            led.order(rng.choice(trade), rng.choice(["phone", "phone", "phone", "web", "web"]),
                      at(day, rng.randint(9, 16), rng), led.basket("phone", trade=True), trade=True)
        if day == OUTLIER_DAY:  # best day: one trade order, eight lines, most of the day's sales
            led.order(trade[0], "phone", datetime(2026, 8, 14, 10, 42, 7),
                      [(13, 40), (14, 30), (8, 60), (11, 48), (12, 36), (18, 60), (19, 40), (17, 24)], trade=True)

    # cancelled: four in ten had their lines released, so they show a header with no lines
    released = {oid for oid in cancelled if rng.random() < 0.4}
    led.items = [r for r in led.items if r[1] not in released]

    # header totals: from 6 July the phone desk amends orders in a tool that writes lines and leaves the header
    shoppers = set(retail)

    def amendable(lo, hi):
        return [o for o in led.orders if o[2] == "phone" and o[4] == "completed" and o[1] in shoppers
                and lo <= o[3] < hi]
    jul_aug = rng.sample(amendable(ts(utc(datetime(2026, 7, 6))), ts(utc(datetime(2026, 9, 1)))), AMENDED["jul-aug"])
    sep = rng.sample(amendable(ts(utc(datetime(2026, 9, 1))), ts(utc(datetime(2026, 9, 14, 23)))), AMENDED["sep"])
    next_item = max(r[0] for r in led.items) + 1
    for o in sorted(jul_aug + sep, key=lambda o: o[0]):
        when = datetime.strptime(o[3], "%Y-%m-%d %H:%M:%S") + timedelta(hours=rng.randint(2, 30))
        lines = [r for r in led.items if r[1] == o[0]]
        if rng.random() < 0.55:
            product = rng.choices(range(1, len(CATALOGUE) + 1), led.weights)[0]
            qty = rng.choice([1, 1, 2])
            price = led.products[product - 1][4]
            led.items.append([next_item, o[0], product, qty, price, qty * price])
            led.amendments.append([len(led.amendments) + 1, o[0], next_item, ts(when), "item_added", "phone-desk"])
            next_item += 1
        else:
            line = rng.choice(lines)
            line[3] += rng.choice([1, 1, 2])
            line[5] = line[3] * line[4]
            led.amendments.append([len(led.amendments) + 1, o[0], line[0], ts(when), "quantity_changed", "phone-desk"])
    led.items.sort(key=lambda r: r[0])
    return {"customers": led.customers, "products": led.products, "orders": led.orders, "order_items": led.items,
            "order_amendments": led.amendments}
