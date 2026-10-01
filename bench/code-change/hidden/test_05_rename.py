"""05: needs_approval renamed to requires_sign_off, wherever it is imported, re-exported, passed or tested."""
import re

from _support import BACKEND, client


def test_the_new_name():
    from refunds.rules import requires_sign_off
    assert requires_sign_off(1000) and not requires_sign_off(10)


def test_the_package_re_exports_it():
    from refunds import requires_sign_off  # noqa: F401  the reports import it from here


def test_the_old_name_is_gone():
    old = re.compile(r"\bneeds_approval\b")  # a whole name: test_large_refund_needs_approval is a test's own name
    left = [str(f.relative_to(BACKEND)) for f in BACKEND.rglob("*.py") if old.search(f.read_text(encoding="utf-8"))]
    assert not left, f"needs_approval is still in {', '.join(left)}"


def test_the_monthly_report_still_counts():
    from reports import count_large
    assert count_large([100, 300]) == 1


def test_the_endpoints_still_decide():
    c = client()
    assert c.post("/api/refunds", json={"order_id": "D1", "amount": 300}).status_code == 202
    assert c.post("/api/refunds", json={"order_id": "D1", "amount": 20}).status_code == 201
    assert c.post("/api/actions", json={"action": "refund", "order_id": "D1", "amount": 300}).get_json() == \
        {"status": "awaiting approval"}
