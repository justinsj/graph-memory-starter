"""02: queued refunds name who must sign them. queue_for_approval takes the approver, and both callers pass it."""
from _support import client


def test_approver_for():
    from refunds.rules import approver_for
    assert approver_for(100) is None
    assert approver_for(250) is None
    assert approver_for(300) == "Ops Manager"
    assert approver_for(1000) == "Ops Manager"
    assert approver_for(1500) == "Director"


def test_the_director_threshold_is_a_setting():
    import config
    assert config.DIRECTOR_THRESHOLD_GBP == 1000


def test_the_queue_keeps_the_approver():
    import approvals
    approvals.PENDING.clear()
    approvals.queue_for_approval({"order_id": "X", "amount": 2000}, "Director")
    assert approvals.PENDING == [{"refund": {"order_id": "X", "amount": 2000}, "approver": "Director"}]


def test_the_refunds_endpoint_names_the_approver():
    c = client()
    import approvals
    r = c.post("/api/refunds", json={"order_id": "B2", "amount": 1500})
    assert r.status_code == 202
    assert r.get_json() == {"status": "awaiting approval", "approver": "Director"}
    assert approvals.PENDING[-1] == {"refund": {"order_id": "B2", "amount": 1500}, "approver": "Director"}


def test_the_quick_refund_names_the_approver():
    c = client()
    import approvals
    r = c.post("/api/actions", json={"action": "refund", "order_id": "B3", "amount": 300})
    assert r.get_json() == {"status": "awaiting approval", "approver": "Ops Manager"}
    assert approvals.PENDING[-1]["approver"] == "Ops Manager"
    assert approvals.PENDING[-1]["refund"]["order_id"] == "B3"


def test_small_refunds_are_not_queued():
    c = client()
    import approvals
    assert c.post("/api/refunds", json={"order_id": "B4", "amount": 50}).status_code == 201
    assert c.post("/api/actions", json={"action": "refund", "order_id": "B5", "amount": 50}).get_json() == \
        {"status": "refunded"}
    assert approvals.PENDING == []
