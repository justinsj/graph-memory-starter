"""A SaaS company's billing, March 2025 to September 2026: a hundred-odd accounts that trial,
convert, change seats, fall behind on payment, pause and cancel, then the accounts each
rule in questions.json needs, each marked with the rule it is there for.

Deterministic: the same rows on every build.
"""
import calendar
import random
from datetime import datetime, timedelta

NOW = datetime(2026, 9, 30, 17, 0)
PLANS = {  # id: (name, interval, minor units per seat per interval, currency)
    "starter-monthly": ("Starter", "month", 1900, "USD"),
    "team-monthly": ("Team", "month", 4900, "USD"),
    "team-annual": ("Team, annual", "year", 46800, "USD"),
    "business-annual": ("Business, annual", "year", 118800, "USD"),
    "starter-monthly-eur": ("Starter", "month", 1700, "EUR"),
    "team-monthly-eur": ("Team", "month", 4500, "EUR"),
    "team-annual-eur": ("Team, annual", "year", 43200, "EUR"),
    "starter-monthly-gbp": ("Starter", "month", 1500, "GBP"),
    "team-monthly-gbp": ("Team", "month", 3900, "GBP"),
    "team-annual-gbp": ("Team, annual", "year", 37200, "GBP"),
}
WORDS = ["Northgate", "Bluebell", "Copperleaf", "Riverside", "Summit", "Hollow Oak", "Ember", "Saltmarsh",
         "Larkspur", "Granite", "Meadow", "Juniper", "Harrow", "Linden", "Cobalt", "Thistle", "Beacon",
         "Kingfisher", "Moorland", "Orchard", "Foxglove", "Ironbridge", "Willow", "Seaview"]
KINDS = ["Dental", "Studio", "Logistics", "Consulting", "Vets", "Tutors", "Estates", "Print", "Builders",
         "Opticians", "Media", "Accounting", "Travel", "Gym", "Florists", "Law"]


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def at(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


def add_months(dt, n):
    y, m = divmod(dt.month - 1 + n, 12)
    y, m = dt.year + y, m + 1
    return dt.replace(year=y, month=m, day=min(dt.day, calendar.monthrange(y, m)[1]))


class Sub:
    """A subscription as a list of states, each from its time to the next one's."""

    def __init__(self, sid, account_id, plan, qty, start, status):
        self.id, self.account_id, self.created_at = sid, account_id, start
        self.segments = [[start, plan, qty, status]]
        self.anchor = start if status == "active" else None
        self.trial_end = self.canceled_at = self.cancel_at = self.ended_at = None
        self.cancel_at_period_end = 0

    @property
    def state(self):
        return self.segments[-1]

    def set(self, when, plan=None, qty=None, status=None):
        _, p, q, s = self.state
        self.segments.append([when, plan or p, qty or q, status or s])
        if status == "active" and self.anchor is None:
            self.anchor = when

    def period_end_after(self, when):
        step = 12 if PLANS[self.state[1]][1] == "year" else 1
        k = 1
        while add_months(self.anchor, k * step) <= when:
            k += 1
        return add_months(self.anchor, k * step)

    def cancel(self, requested, at_period_end=True):
        """Cancel now, or at the end of the period already paid for."""
        self.canceled_at = requested
        end = requested
        if at_period_end:
            end = self.period_end_after(requested)
            self.cancel_at_period_end, self.cancel_at = 1, end
        if end <= NOW:
            self.set(end, status="canceled")
            self.ended_at = end


class Billing:

    def __init__(self):
        self.accounts, self.subs, self.discounts = [], [], []

    def account(self, name, created_at):
        self.accounts.append((len(self.accounts) + 1, name, ts(created_at)))
        return len(self.accounts)

    def subscribe(self, account_id, plan, qty, start, trial_days=0):
        sub = Sub(len(self.subs) + 1, account_id, plan, qty, start, "trialing" if trial_days else "active")
        if trial_days:
            sub.trial_end = start + timedelta(days=trial_days)
        self.subs.append(sub)
        return sub

    def discount(self, sub, percent_off, starts_at, ends_at):
        self.discounts.append((len(self.discounts) + 1, sub.id, percent_off, ts(starts_at), ts(ends_at)))

    def rows(self):
        subs, history = [], []
        for s in self.subs:
            _, plan, qty, status = s.state
            subs.append((s.id, s.account_id, plan, status, qty, ts(s.created_at), ts(s.trial_end), ts(s.canceled_at),
                         s.cancel_at_period_end, ts(s.cancel_at), ts(s.ended_at)))
            for i, (start, plan, qty, status) in enumerate(s.segments):
                end = s.segments[i + 1][0] if i + 1 < len(s.segments) else None
                history.append((s.id, plan, qty, status, ts(start), ts(end)))
        plans = [(pid, name, interval, amount, cur) for pid, (name, interval, amount, cur) in PLANS.items()]
        return {"accounts": self.accounts, "plans": plans, "subscriptions": subs,
                "subscription_history": history, "discounts": self.discounts}


def background(b, rng):
    names = set()
    for _ in range(110):
        name = f"{rng.choice(WORDS)} {rng.choice(KINDS)}"
        if name in names:
            continue
        names.add(name)
        created = datetime(2025, 3, 1) + timedelta(days=rng.randint(0, 567), seconds=rng.randint(0, 86399))
        acct = b.account(name, created)
        start = created + timedelta(minutes=rng.randint(5, 600))
        if start > NOW:
            continue
        plan = rng.choice(["starter-monthly"] * 8 + ["team-monthly"] * 7 + ["team-annual"] * 3 + ["business-annual"] * 2)
        qty = {"starter-monthly": rng.randint(1, 3), "team-monthly": rng.randint(3, 15),
               "team-annual": rng.randint(3, 15), "business-annual": rng.randint(10, 40)}[plan]
        if rng.random() < 0.8:
            sub = b.subscribe(acct, plan, qty, start, trial_days=14)
            if sub.trial_end > NOW:
                continue
            if rng.random() > 0.72:
                sub.cancel(sub.trial_end, at_period_end=False)  # the trial ran out
                continue
            sub.set(sub.trial_end, status="active")
        else:
            sub = b.subscribe(acct, plan, qty, start)
        if rng.random() < 0.12:
            pct, months = rng.choice([(20, 3), (50, 1), (10, None)])
            b.discount(sub, pct, sub.anchor, add_months(sub.anchor, months) if months else None)
        t = sub.anchor
        while True:
            t += timedelta(days=rng.randint(20, 40), seconds=rng.randint(0, 86399))
            if t > NOW:
                break
            annual = PLANS[sub.state[1]][1] == "year"
            roll = rng.random()
            if roll < (0.012 if annual else 0.035):
                sub.cancel(t)
                break
            if roll < 0.065:  # a failed renewal: dunning, then paid or ended
                sub.set(t, status="past_due")
                back = t + timedelta(days=rng.randint(3, 18), seconds=rng.randint(0, 86399))
                if back > NOW:
                    break
                if rng.random() < 0.75:
                    sub.set(back, status="active")
                    t = back
                    continue
                sub.cancel(back, at_period_end=False)
                break
            if roll < 0.08 and not annual:
                sub.set(t, status="paused")
                back = t + timedelta(days=rng.randint(30, 90))
                if back > NOW:
                    break
                sub.set(back, status="active")
                t = back
            elif roll < 0.16:
                sub.set(t, qty=max(1, sub.state[2] + rng.choice([-2, -1, 1, 1, 2, 3, 4])))
            elif roll < 0.18:
                up = {"starter-monthly": "team-monthly", "team-monthly": "team-annual"}.get(sub.state[1])
                if up:
                    sub.set(t, plan=up)
                    if up == "team-annual":
                        sub.anchor = t  # a new annual period starts at the upgrade


def traps(b):
    """The accounts each rule needs, around 31 August 2026."""
    # mrr-as-of: 5 seats on 31 August, 12 now
    s = b.subscribe(b.account("Northwind Dental", at("2026-02-10 09:00")), "team-monthly", 5, at("2026-02-10 09:30"))
    s.set(at("2026-09-10 14:00"), qty=12)
    # mrr-as-of, churn-ended: asked to cancel on 20 August, paid up to 3 September
    s = b.subscribe(b.account("Brightside Tutors", at("2025-11-03 10:00")), "starter-monthly", 3, at("2025-11-03 10:20"))
    s.cancel(at("2026-08-20 16:45"))
    # mrr-as-of: a customer from 5 September
    b.subscribe(b.account("Quill & Ink", at("2026-09-05 08:00")), "business-annual", 10, at("2026-09-05 08:10"))
    # mrr-annual: billed once a year
    b.subscribe(b.account("Harbour Freight Co", at("2025-12-01 11:00")), "business-annual", 8, at("2025-12-01 11:30"))
    # mrr-past-due: a failed renewal on 25 August, paid on 3 September
    s = b.subscribe(b.account("Pinecone Labs", at("2026-01-14 15:00")), "team-monthly", 6, at("2026-01-14 15:10"))
    s.set(at("2026-08-25 06:00"), status="past_due")
    s.set(at("2026-09-03 12:00"), status="active")
    # mrr-past-due, churn-past-due: in dunning on 31 August, ended unpaid on 15 September
    s = b.subscribe(b.account("Oakridge Clinics", at("2025-10-27 09:00")), "team-monthly", 4, at("2025-10-27 09:05"))
    s.set(at("2026-08-27 06:00"), status="past_due")
    s.cancel(at("2026-09-15 06:00"), at_period_end=False)
    # mrr-not-paying: on trial on 31 August, converted on 8 September
    s = b.subscribe(b.account("Lumen Studio", at("2026-08-25 11:00")), "team-monthly", 3, at("2026-08-25 11:05"), trial_days=14)
    s.set(s.trial_end, status="active")
    # mrr-not-paying, churn-paused: paused from 15 August to 15 September
    s = b.subscribe(b.account("Fernhill Farm Shop", at("2025-12-19 13:00")), "starter-monthly", 2, at("2025-12-19 13:15"))
    s.set(at("2026-08-15 09:00"), status="paused")
    s.set(at("2026-09-15 09:00"), status="active")
    # mrr-discounts: 20% off through the quarter, 50% off that ended on 10 August, 25% off from 1 September
    s = b.subscribe(b.account("Atlas Recruitment", at("2025-07-01 10:00")), "team-annual", 10, at("2025-07-01 10:30"))
    b.discount(s, 20, at("2026-07-01 00:00"), at("2026-10-01 00:00"))
    s = b.subscribe(b.account("Kestrel Legal", at("2026-03-10 12:00")), "team-monthly", 7, at("2026-03-10 12:20"))
    b.discount(s, 50, at("2026-07-10 00:00"), at("2026-08-10 00:00"))
    s = b.subscribe(b.account("Marlow Bakery", at("2026-04-22 08:00")), "starter-monthly", 2, at("2026-04-22 08:30"))
    b.discount(s, 25, at("2026-09-01 00:00"), None)
    # churn-ended: asked to cancel on 18 July, left on 9 August
    s = b.subscribe(b.account("Tidewater Surf", at("2025-10-09 13:00")), "team-monthly", 4, at("2025-10-09 13:00"))
    s.cancel(at("2026-07-18 10:00"))
    # churn-logos: a second office's subscription ends; the first carries on
    acct = b.account("Greenway Architects", at("2025-06-12 09:00"))
    b.subscribe(acct, "team-monthly", 6, at("2025-06-12 09:10"))
    s = b.subscribe(acct, "starter-monthly", 2, at("2026-02-20 09:00"))
    s.cancel(at("2026-08-04 17:00"))
    # churn-logos: monthly to annual, done as a cancel and a new subscription the same minute
    acct = b.account("Birch & Co Accountants", at("2025-09-06 10:00"))
    s = b.subscribe(acct, "team-monthly", 5, at("2025-09-06 10:00"))
    s.cancel(at("2026-08-06 10:00"), at_period_end=False)
    b.subscribe(acct, "team-annual", 5, at("2026-08-06 10:00"))
    # churn-trials: a trial that ran out in August, never paid
    s = b.subscribe(b.account("Sparrow Yoga", at("2026-07-28 18:00")), "starter-monthly", 1, at("2026-07-28 18:05"), trial_days=14)
    s.cancel(s.trial_end, at_period_end=False)
    # churn-past-due: in dunning on 1 August, ended unpaid on 14 August
    s = b.subscribe(b.account("Redfern Physio", at("2025-12-02 10:00")), "team-monthly", 3, at("2025-12-02 10:10"))
    s.set(at("2026-07-26 06:00"), status="past_due")
    s.cancel(at("2026-08-14 06:00"), at_period_end=False)


def local_currency(b, rng):
    """About a quarter of the accounts are billed in euros or pounds, on the same plans.
    budget-rates: the handbook turns them into dollars at finance's fixed rates."""
    for acct, _, _ in b.accounts:
        roll = rng.random()
        cur = "eur" if roll < 0.15 else "gbp" if roll < 0.25 else None
        for sub in (s for s in b.subs if s.account_id == acct and cur):
            for seg in sub.segments:
                if f"{seg[1]}-{cur}" in PLANS:
                    seg[1] = f"{seg[1]}-{cur}"


def rows():
    b = Billing()
    background(b, random.Random(20260901))
    local_currency(b, random.Random(7))
    traps(b)
    return b.rows()
