"""01: refunds in euros. needs_approval takes a currency, and everything that decides approval passes it."""
import re

from _support import client, raises, ts, ts_function


def test_euros_are_converted_before_the_threshold():
    from refunds.rules import needs_approval
    assert needs_approval(300, "EUR")          # 255 GBP
    assert not needs_approval(290, "EUR")      # 246.50 GBP


def test_pounds_when_no_currency_is_given():
    from refunds.rules import needs_approval
    assert needs_approval(251) and not needs_approval(250)
    assert needs_approval(251, "GBP")


def test_other_currencies_are_refused():
    from refunds.rules import needs_approval
    assert raises(needs_approval, 300, "USD")


def test_the_rate_is_a_setting():
    import config
    assert config.EUR_TO_GBP == 0.85


def test_the_refunds_endpoint_uses_the_currency():
    c = client()
    assert c.post("/api/refunds", json={"order_id": "A1", "amount": 290, "currency": "EUR"}).status_code == 201
    assert c.post("/api/refunds", json={"order_id": "A1", "amount": 300, "currency": "EUR"}).status_code == 202


def test_the_refunds_endpoint_assumes_pounds():
    assert client().post("/api/refunds", json={"order_id": "A1", "amount": 260}).status_code == 202


def test_the_quick_refund_uses_the_currency():
    c = client()
    small = c.post("/api/actions", json={"action": "refund", "order_id": "A1", "amount": 290, "currency": "EUR"})
    large = c.post("/api/actions", json={"action": "refund", "order_id": "A1", "amount": 300, "currency": "EUR"})
    assert small.get_json()["status"] == "refunded"
    assert large.get_json()["status"] == "awaiting approval"


def test_the_monthly_report_still_counts():
    """It passed needs_approval to filter(), one amount at a time. Either design is right: amounts in pounds as
    before (so the currency must stay optional), or refunds with their currency, as the report now decides approval."""
    from reports import count_large
    try:
        assert count_large([100, 300]) == 1
    except (TypeError, KeyError, AttributeError, IndexError):
        assert count_large([{"order_id": "a", "amount": 100}, {"order_id": "b", "amount": 300}]) == 1
        assert count_large([{"order_id": "a", "amount": 290, "currency": "EUR"},
                            {"order_id": "b", "amount": 300, "currency": "EUR"}]) == 1


def test_the_frontend_sends_a_currency_with_every_refund():
    api = ts("api.ts")
    for name in ("submitRefund", "refundViaActions"):
        fn = ts_function(api, name)
        assert fn, f"{name} is gone"
        assert re.search(r"(JSON\.stringify|postAction)\(\s*\{[^}]*\bcurrency\b", fn, re.S), \
            f"{name} does not send a currency"
