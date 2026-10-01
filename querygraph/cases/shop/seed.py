"""The shop's ledger, July to September 2026: three months of ordinary trade, then the
rows each rule in questions.json needs, each marked with the rule it is there for.

Deterministic: the same rows on every build.
"""
import math
import random
from datetime import date, datetime, timedelta

NOW = datetime(2026, 9, 30, 17, 0)
BANK_HOLIDAYS = {date(2026, 8, 31)}  # the summer bank holiday: no reference rate is published

FIRST = ["Olivia", "Amelia", "Isla", "Ava", "Mia", "Ivy", "Lily", "Freya", "Noah", "Oliver", "George", "Leo",
         "Arthur", "Muhammad", "Harry", "Jack", "Thomas", "Oscar", "Sophie", "Grace", "Ella", "Priya", "Tom", "Ruth"]
LAST = ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies", "Patel", "Wright",
        "Walker", "Evans", "Khan", "Hughes", "Green", "Hall", "Clarke", "Lewis", "Murphy", "Byrne"]
EU_FIRST = ["Aoife", "Seán", "Camille", "Lucas", "Hugo", "Léa", "Emma", "Jonas", "Lena", "Finn", "Clara", "Daan"]
EU_LAST = ["Kelly", "O'Brien", "Martin", "Bernard", "Dubois", "Müller", "Schmidt", "Weber", "de Vries", "Bakker"]
MAIL = ["gmail.com", "outlook.com", "icloud.com", "yahoo.co.uk", "proton.me", "btinternet.com", "hotmail.com"]
COUNTRIES = ["GB"] * 72 + ["IE"] * 10 + ["FR"] * 8 + ["DE"] * 6 + ["NL"] * 4
PRICES = [1299, 1899, 2450, 3200, 3999, 4599, 5400, 6250, 7999, 8900, 11999, 14500]


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def at(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


class Ledger:

    def __init__(self):
        self.customers, self.orders, self.payments, self.refunds = [], [], [], []

    def customer(self, email, name, country, created_at):
        self.customers.append([len(self.customers) + 1, email, name, country, ts(created_at)])
        return len(self.customers)

    def currency(self, customer_id):
        return "GBP" if self.customers[customer_id - 1][3] == "GB" else "EUR"

    def order(self, customer_id, total, placed_at, payment="captured", captured_at=None):
        """An order and its one payment. Returns the payment's id."""
        cur = self.currency(customer_id)
        oid, pid = len(self.orders) + 1, len(self.payments) + 1
        status = {"captured": "shipped", "authorized": "placed", "voided": "cancelled", "failed": "cancelled"}[payment]
        self.orders.append([oid, customer_id, ts(placed_at), status, cur, total])
        created = placed_at + timedelta(seconds=4)
        captured = ts(captured_at or created + timedelta(seconds=40)) if payment == "captured" else None
        self.payments.append([pid, oid, total, cur, payment, ts(created), captured])
        return pid

    def refund(self, payment_id, amount, created_at, status="succeeded"):
        self.refunds.append([len(self.refunds) + 1, payment_id, amount, status, ts(created_at)])
        pay = self.payments[payment_id - 1]
        refunded = sum(r[2] for r in self.refunds if r[1] == payment_id and r[3] == "succeeded")
        if refunded >= pay[2]:
            self.orders[pay[1] - 1][3] = "refunded"


def background(led, rng):
    """Three months of trade: 1 to 4 orders a day, some captured on dispatch, some refunded."""
    for n in range(90):
        country = rng.choice(COUNTRIES)
        first, last = (rng.choice(FIRST), rng.choice(LAST)) if country == "GB" else (rng.choice(EU_FIRST), rng.choice(EU_LAST))
        handle = f"{first}.{last}".lower().replace("'", "").replace(" ", "")
        handle = handle.translate(str.maketrans("éáüö", "eauo"))
        led.customer(f"{handle}{rng.randint(1, 99)}@{rng.choice(MAIL)}", f"{first} {last}", country,
                     datetime(2025, 1, 1) + timedelta(days=rng.randint(0, 540)))
    day = datetime(2026, 7, 1)
    while day < datetime(2026, 10, 1):
        for _ in range(rng.randint(1, 4)):
            placed = day + timedelta(seconds=rng.randint(0, 86399))
            if placed > NOW:
                continue
            total = sum(rng.choice(PRICES) for _ in range(rng.choice([1, 1, 1, 2, 2, 3])))
            customer = rng.randint(1, 90)
            roll = rng.random()
            if roll < 0.03:
                led.order(customer, total, placed, "failed")
                continue
            if roll < 0.05:
                led.order(customer, total, placed, "voided" if placed < NOW - timedelta(days=4) else "authorized")
                continue
            # most cards are captured at checkout, the rest when the parcel ships
            captured = placed + (timedelta(seconds=rng.randint(20, 90)) if rng.random() < 0.75
                                 else timedelta(hours=rng.randint(20, 72), minutes=rng.randint(0, 59)))
            if captured > NOW:
                led.order(customer, total, placed, "authorized")
                continue
            pid = led.order(customer, total, placed, "captured", captured)
            if rng.random() < 0.09:
                when = captured + timedelta(days=rng.randint(1, 25), seconds=rng.randint(0, 86399))
                if when > NOW:
                    continue
                amount = total if rng.random() < 0.6 else round(total * rng.choice([0.2, 0.25, 0.3, 0.5]))
                status = "succeeded" if rng.random() < 0.92 else "failed"
                if when > NOW - timedelta(days=3) and rng.random() < 0.5:
                    status = "pending"
                led.refund(pid, amount, when, status)
        day += timedelta(days=1)


def traps(led):
    """The rows each rule needs, around August 2026."""
    gb = next(c[0] for c in led.customers if c[3] == "GB")
    gb2 = next(c[0] for c in led.customers if c[3] == "GB" and c[0] != gb)
    eu = next(c[0] for c in led.customers if c[3] == "IE")
    eu2 = next(c[0] for c in led.customers if c[3] in ("FR", "DE"))

    # london-months: 00:40 on 1 August in London is still 31 July in UTC ...
    led.order(gb, 6400, at("2026-07-31 23:05"), "captured", at("2026-07-31 23:40"))
    # ... and 00:20 on 1 September in London is 31 August in UTC
    led.order(gb2, 12000, at("2026-08-31 23:10"), "captured", at("2026-08-31 23:20"))

    # captured-when: ordered in July, card captured when the parcel left in August ...
    led.order(gb, 8900, at("2026-07-29 14:00"), "captured", at("2026-08-03 09:12"))
    # ... and ordered in August, captured in September
    led.order(gb2, 14200, at("2026-08-28 16:30"), "captured", at("2026-09-02 10:00"))

    # captured-only: an authorisation the customer cancelled before dispatch, and a declined card
    led.order(gb, 25000, at("2026-08-19 10:00"), "voided")
    led.order(gb2, 7500, at("2026-08-12 18:30"), "failed")

    # fx-as-of: euro captures on a Saturday, a Sunday and the bank holiday, when no rate is published
    led.order(eu, 18000, at("2026-08-08 11:00"), "captured")
    led.order(eu2, 9550, at("2026-08-16 19:30"), "captured")
    led.order(eu, 21000, at("2026-08-31 09:45"), "captured")

    # refunds-when: a July order refunded in August comes off August ...
    july = led.order(gb, 4500, at("2026-07-22 12:00"), "captured")
    led.refund(july, 4500, at("2026-08-05 15:20"))
    # ... an August order refunded in September does not
    august = led.order(gb2, 6600, at("2026-08-20 08:15"), "captured")
    led.refund(august, 6600, at("2026-09-03 11:00"))

    # refunds-succeeded: a refund still pending at the bank and one that bounced
    p1 = led.order(gb, 6000, at("2026-08-02 13:00"), "captured")
    led.refund(p1, 6000, at("2026-08-30 16:00"), "pending")
    p2 = led.order(gb2, 3000, at("2026-08-04 10:00"), "captured")
    led.refund(p2, 3000, at("2026-08-14 09:00"), "failed")

    # not-revenue: a staff order, and QA's test purchase on production, refunded only in September
    staff = led.customer("anna.kowalski@shop.example", "Anna Kowalski", "GB", datetime(2024, 3, 1))
    qa = led.customer("qa+checkout-0812@mailinator.com", "QA Checkout", "GB", datetime(2026, 8, 12))
    led.order(staff, 3000, at("2026-08-11 12:30"), "captured")
    test = led.order(qa, 99900, at("2026-08-12 10:02"), "captured")
    led.refund(test, 99900, at("2026-09-01 09:30"))


def fx_rates():
    """Pounds per euro for each business day: none on weekends or bank holidays."""
    rows, day, i = [], date(2026, 6, 26), 0
    while day <= date(2026, 9, 30):
        if day.weekday() < 5 and day not in BANK_HOLIDAYS:
            rows.append(("EUR", day.isoformat(), round(0.8560 + 0.0060 * math.sin(i / 6.0) + 0.0020 * math.sin(i / 2.3), 4)))
        day += timedelta(days=1)
        i += 1
    return rows


def rows():
    led = Ledger()
    background(led, random.Random(20260831))
    traps(led)
    return {"customers": led.customers, "orders": led.orders, "payments": led.payments,
            "refunds": led.refunds, "fx_rates": fx_rates()}
