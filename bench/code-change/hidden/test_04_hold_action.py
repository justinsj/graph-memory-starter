"""04: a Hold button on the order page, through the quick actions endpoint: backend branch, client function, button."""
import re

from _support import client, ts, ts_function


def test_the_hold_action():
    r = client().post("/api/actions", json={"action": "hold", "order_id": "9"})
    assert r.status_code == 200
    assert r.get_json() == {"order_id": "9", "status": "on hold"}


def test_cancel_still_works():
    assert client().post("/api/actions", json={"action": "cancel", "order_id": "9"}).get_json() == \
        {"order_id": "9", "status": "cancelled"}


def test_an_unknown_action_is_still_refused():
    assert client().post("/api/actions", json={"action": "explode", "order_id": "9"}).status_code == 400


def test_the_client_function():
    fn = ts_function(ts("api.ts"), "holdOrder")
    assert fn, "no holdOrder in api.ts"
    assert re.search(r"""action\s*:\s*["']hold["']""", fn), "holdOrder does not send action: hold"


def test_the_button():
    page = ts("components/OrderPage.tsx")
    assert re.search(r"import\s*\{[^}]*\bholdOrder\b[^}]*\}\s*from", page), "OrderPage does not import holdOrder"
    buttons = re.findall(r"<button\b.*?</button>", page, re.S)
    assert any(re.search(r"onClick=\{[^}]*\bholdOrder\(", b) for b in buttons), "no button runs holdOrder"
