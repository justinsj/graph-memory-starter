"""A help desk with two brands, July to September 2026: about two hundred tickets with their
replies, notes, auto-acknowledgements, escalations, merges and spam, then the tickets each
rule in questions.json needs, each marked with the rule it is there for.

Deterministic: the same rows on every build.
"""
import random
from datetime import datetime, timedelta

NOW = datetime(2026, 9, 30, 17, 0)
AGENTS = [("Maya Okafor", "agent"), ("Dan Whitlock", "agent"), ("Sofia Reyes", "agent"), ("Kieran Doyle", "agent"),
          ("Hana Sato", "agent"), ("Leon Brandt", "agent"), ("Priya Nair", "admin")]
FIRST = ["Alex", "Sam", "Jordan", "Chris", "Morgan", "Robin", "Jamie", "Taylor", "Casey", "Drew", "Ellis", "Frankie"]
LAST = ["Hart", "Quinn", "Moss", "Reid", "Lowe", "Fox", "Shaw", "Kerr", "Nash", "Pike", "Rowe", "Vance"]
COMPANIES = ["acme-freight.com", "brightpath.io", "cedarhealth.org", "dunmore.co.uk", "elmtree.dev", "fjordpay.com"]
SUBJECTS = {
    "urgent": ["Checkout is down for all customers", "Cannot log in, whole team locked out", "Payments failing since 9am",
               "API returning 500 on every call", "Data export stuck, board meeting at noon"],
    "high": ["Webhook deliveries delayed", "SSO login loop for some users", "Invoice shows the wrong VAT"],
    "normal": ["How do I add a user?", "Change the billing email", "Report filters not saving", "CSV import question"],
    "low": ["Feature request: dark mode", "Typo on the settings page", "Can we get a copy of our DPA?"],
}
ACK = "Thanks for getting in touch. We've got your request and a person will reply soon."


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def at(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


class Desk:

    def __init__(self):
        self.users, self.tickets, self.comments, self.changes = [], [], [], []

    def user(self, name, email, role):
        self.users.append((len(self.users) + 1, name, email, role))
        return len(self.users)

    def ticket(self, requester, brand, channel, priority, created, subject=None, rng=None):
        """A ticket, its description, its first field values, and the auto-acknowledgement."""
        tid = len(self.tickets) + 1
        subject = subject or (rng.choice(SUBJECTS[priority]) if rng else SUBJECTS[priority][0])
        self.tickets.append([tid, requester, brand, subject, channel, priority, "new", ts(created), None])
        self.comment(tid, requester, 1, channel, subject + ". Details in the message below.", created)
        self.changes.append((tid, "priority", None, priority, ts(created)))
        self.changes.append((tid, "status", None, "new", ts(created)))
        if channel in ("email", "web"):  # the trigger that acknowledges every email and web form
            self.comment(tid, self.bot, 1, "rule", ACK, created + timedelta(seconds=25))
        return tid

    def comment(self, tid, author, public, via, body, when):
        self.comments.append((len(self.comments) + 1, tid, author, public, via, body, ts(when)))

    def reply(self, tid, agent, when, body="Thanks, I'm on it. Here's what I found so far."):
        self.comment(tid, agent, 1, "web", body, when)
        if self.tickets[tid - 1][6] == "new":
            self.status(tid, "open", when)

    def note(self, tid, agent, when, body="Checking with engineering before I reply."):
        self.comment(tid, agent, 0, "web", body, when)

    def priority(self, tid, value, when):
        self.changes.append((tid, "priority", self.tickets[tid - 1][5], value, ts(when)))
        self.tickets[tid - 1][5] = value

    def status(self, tid, value, when):
        self.changes.append((tid, "status", self.tickets[tid - 1][6], value, ts(when)))
        self.tickets[tid - 1][6] = value

    def merge(self, dup, into, agent, when):
        self.note(dup, agent, when, f"Closed and merged into #{into}.")
        self.status(dup, "closed", when)
        self.tickets[dup - 1][8] = into


def delay(rng, priority):
    if priority == "urgent":
        return timedelta(minutes=rng.randint(5, 55) if rng.random() < 0.72 else rng.randint(62, 240))
    return {"high": timedelta(minutes=rng.randint(20, 360)), "normal": timedelta(hours=rng.uniform(1, 26)),
            "low": timedelta(hours=rng.uniform(2, 48))}[priority]


def background(d, rng):
    requesters = [d.user(f"{f} {l}", f"{f.lower()}.{l.lower()}@{rng.choice(COMPANIES)}", "end-user")
                  for f in FIRST for l in LAST[:6]]
    humans = list(range(1, len(AGENTS) + 1))
    day = datetime(2026, 7, 1)
    while day < datetime(2026, 10, 1):
        for _ in range(rng.randint(1, 4)):
            created = day + timedelta(seconds=rng.randint(0, 86399))
            if created > NOW:
                continue
            brand = "enterprise" if rng.random() < 0.3 else "standard"
            channel = rng.choice(["email"] * 9 + ["web"] * 7 + ["chat"] * 2 + ["api"] * 2)
            roll = rng.random()
            urgent_share = 0.16 if brand == "enterprise" else 0.08
            priority = ("urgent" if roll < urgent_share else "high" if roll < urgent_share + 0.15
                        else "normal" if roll < urgent_share + 0.70 else "low")
            agent = rng.choice(humans)
            if rng.random() < 0.02:  # spam through the web form, often shouting
                tid = d.ticket(rng.choice(requesters), brand, "web", rng.choice(["urgent", "normal"]), created,
                               "URGENT: grow your traffic 300% this week")
                d.status(tid, "deleted", created + timedelta(hours=rng.randint(2, 8)))
                continue
            tid = d.ticket(rng.choice(requesters), brand, channel, priority, created, rng=rng)
            clock = created
            fate = rng.random()
            if priority in ("normal", "high") and fate < 0.06:  # raised to urgent before anyone replied
                clock = created + timedelta(minutes=rng.randint(60, 1200))
                if clock > NOW:
                    continue
                d.priority(tid, "urgent", clock)
                priority = "urgent"
            replied = clock + delay(rng, priority)
            if rng.random() < 0.25 and clock + (replied - clock) / 3 < NOW:
                d.note(tid, agent, clock + (replied - clock) / 3)
            if rng.random() < 0.12 and clock + (replied - clock) / 2 < NOW:
                d.comment(tid, d.tickets[tid - 1][1], 1, channel, "Any update on this?", clock + (replied - clock) / 2)
            if replied > NOW:
                continue
            if rng.random() < 0.02:  # sorted out on the phone, only a note to show for it
                d.note(tid, agent, replied, "Called the customer and fixed it on the phone.")
                d.status(tid, "solved", replied + timedelta(minutes=5))
                continue
            d.reply(tid, agent, replied)
            if priority == "urgent" and clock == created and rng.random() < 0.3:  # triage takes it down a level
                d.priority(tid, "high", replied + timedelta(minutes=rng.randint(5, 90)))
            elif priority != "urgent" and fate > 0.97:  # got worse after the first reply
                later = replied + timedelta(hours=rng.randint(1, 30))
                if later < NOW:
                    d.priority(tid, "urgent", later)
                    if later + timedelta(minutes=40) < NOW:
                        d.reply(tid, agent, later + timedelta(minutes=40))
            solved = replied + timedelta(hours=rng.randint(1, 72))
            if solved < NOW:
                d.status(tid, "solved", solved)
            if rng.random() < 0.05:  # the requester writes in again about the same thing
                dup_at = created + timedelta(minutes=rng.randint(2, 20))
                if dup_at + timedelta(minutes=40) < NOW:
                    dup = d.ticket(d.tickets[tid - 1][1], brand, channel, d.tickets[tid - 1][5], dup_at, rng=rng)
                    d.merge(dup, tid, agent, dup_at + timedelta(minutes=rng.randint(5, 40)))
        day += timedelta(days=1)


def traps(d):
    """The tickets each rule needs, in August 2026."""
    maya, dan, sofia = 1, 2, 3
    ent = d.user("Grace Whitfield", "grace.whitfield@harbourbank.co.uk", "end-user")
    std = d.user("Owen Price", "owen.price@pricefloors.co.uk", "end-user")

    # human-reply: the bot acknowledged in 25 seconds, a person replied after 95 minutes
    t = d.ticket(ent, "enterprise", "email", "urgent", at("2026-08-04 10:00"), "Payments failing since 9am")
    d.reply(t, maya, at("2026-08-04 11:35"))
    # public-reply: an internal note at 10 minutes, the first reply the customer saw at 75
    t = d.ticket(std, "standard", "web", "urgent", at("2026-08-06 14:00"), "Checkout is down for all customers")
    d.note(t, dan, at("2026-08-06 14:10"))
    d.reply(t, dan, at("2026-08-06 15:15"))
    # human-reply: the requester chased at 25 minutes (chat has no acknowledgement), a person replied at 80
    t = d.ticket(std, "standard", "chat", "urgent", at("2026-08-09 08:00"), "Cannot log in, whole team locked out")
    d.comment(t, std, 1, "chat", "Hello?? Is anyone there?", at("2026-08-09 08:25"))
    d.reply(t, sofia, at("2026-08-09 09:20"))
    # clock-from-urgent: normal for a day, raised to urgent, answered 40 minutes later
    t = d.ticket(ent, "enterprise", "email", "normal", at("2026-08-10 09:00"), "Report filters not saving")
    d.priority(t, "urgent", at("2026-08-11 13:00"))
    d.reply(t, maya, at("2026-08-11 13:40"))
    # urgent-by-history: urgent when it came in, taken down to high at triage (one met, one missed)
    t = d.ticket(ent, "enterprise", "email", "urgent", at("2026-08-07 16:00"), "API returning 500 on every call")
    d.reply(t, dan, at("2026-08-07 16:15"))
    d.priority(t, "high", at("2026-08-07 16:30"))
    t = d.ticket(std, "standard", "email", "urgent", at("2026-08-20 07:30"), "Data export stuck, board meeting at noon")
    d.reply(t, sofia, at("2026-08-20 10:00"))
    d.priority(t, "normal", at("2026-08-20 10:20"))
    # already-answered: replied to as a normal ticket, raised to urgent the next day
    t = d.ticket(std, "standard", "web", "normal", at("2026-08-03 11:00"), "CSV import question")
    d.reply(t, dan, at("2026-08-03 13:30"))
    d.priority(t, "urgent", at("2026-08-04 09:00"))
    d.reply(t, dan, at("2026-08-04 09:50"))
    # not-counted: a duplicate merged into the original, which was answered in 30 minutes ...
    orig = d.ticket(ent, "enterprise", "email", "urgent", at("2026-08-18 10:00"), "SSO login loop for everyone")
    dup = d.ticket(ent, "enterprise", "email", "urgent", at("2026-08-18 10:05"), "RE: SSO login loop for everyone")
    d.merge(dup, orig, maya, at("2026-08-18 10:12"))
    d.reply(orig, maya, at("2026-08-18 10:30"))
    # ... and spam that set its own priority
    t = d.ticket(std, "standard", "web", "urgent", at("2026-08-22 03:00"), "URGENT: grow your traffic 300% this week")
    d.status(t, "deleted", at("2026-08-22 08:00"))
    # no-reply-is-missed: fixed on the phone at night, only an internal note
    t = d.ticket(ent, "enterprise", "email", "urgent", at("2026-08-27 22:00"), "Checkout is down for all customers")
    d.note(t, sofia, at("2026-08-27 22:30"), "Called the customer and fixed it on the phone.")
    d.status(t, "solved", at("2026-08-27 22:35"))


def rows():
    d = Desk()
    for name, role in AGENTS:
        d.user(name, name.lower().replace(" ", ".") + "@support.example", role)
    d.bot = d.user("Support Bot", "bot@support.example", "agent")  # the seat the triggers post as
    background(d, random.Random(20260801))
    traps(d)
    return {"users": d.users, "tickets": d.tickets, "ticket_comments": d.comments, "ticket_field_changes": d.changes}
