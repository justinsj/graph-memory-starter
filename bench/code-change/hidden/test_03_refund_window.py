"""03: the refund window, enforced wherever a refund is validated. The order validation of the same name is untouched."""
from _support import client, raises

OLD = {"order_id": "C1", "amount": 20, "order_age_days": 45}


def test_refund_validation_rejects_old_orders():
    from refunds.rules import validate
    assert raises(validate, {"order_id": "C1", "amount": 20, "order_age_days": 31}, match="outside the refund window")


def test_refund_validation_allows_young_and_undated_orders():
    from refunds.rules import validate
    validate({"order_id": "C1", "amount": 20, "order_age_days": 30})
    validate({"order_id": "C1", "amount": 20})


def test_the_refunds_endpoint_answers_400():
    r = client().post("/api/refunds", json=OLD)
    assert r.status_code == 400
    assert r.get_json() == {"error": "outside the refund window"}


def test_the_refunds_endpoint_still_refunds():
    assert client().post("/api/refunds", json={"order_id": "C1", "amount": 20, "order_age_days": 30}).status_code == 201


def test_the_quick_refund_rejects_old_orders():
    r = client().post("/api/actions", json={"action": "refund", **OLD})
    assert r.status_code == 400
    assert r.get_json() == {"status": "rejected", "error": "outside the refund window"}


def test_the_quick_refund_still_refunds():
    r = client().post("/api/actions", json={"action": "refund", "order_id": "C2", "amount": 20, "order_age_days": 5})
    assert r.status_code == 200 and r.get_json() == {"status": "refunded"}


def test_order_validation_is_unchanged():
    from orders.service import validate as validate_order
    validate_order({"id": "1", "lines": [1]})
    assert raises(validate_order, {"id": "1", "lines": []}, match="an order needs an id and a line")
