"""06: one approval threshold. The backend serves it; the refund form fetches it; the frontend's own constant goes."""
import re

from _support import FRONTEND, client, ts, ts_function


def test_the_config_endpoint():
    r = client().get("/api/config")
    assert r.status_code == 200
    assert r.get_json() == {"approval_threshold_gbp": 250}


def test_the_frontend_constant_is_gone():
    left = [str(f.relative_to(FRONTEND)) for f in FRONTEND.rglob("*.ts*")
            if "APPROVAL_THRESHOLD" in f.read_text(encoding="utf-8")]
    assert not left, f"APPROVAL_THRESHOLD is still in {', '.join(left)}"


def test_the_client_function():
    api = ts("api.ts")
    fn = ts_function(api, "getConfig")
    assert fn, "no getConfig in api.ts"
    urls = re.findall(r"const\s+(\w+)\s*=\s*[`'\"][^`'\"]*/config[`'\"]", api)  # the URL may be a constant
    assert "fetch" in fn and ("/config" in fn or any(re.search(rf"\b{u}\b", fn) for u in urls)), \
        "getConfig does not fetch /config"


def test_the_refund_form_uses_it():
    form = ts("components/RefundForm.tsx")
    assert re.search(r"import\s*\{[^}]*\bgetConfig\b[^}]*\}\s*from", form), "RefundForm does not import getConfig"
    assert re.search(r"\bgetConfig\(\)", form), "RefundForm does not call getConfig"
