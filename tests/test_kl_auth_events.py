"""Who may do what, and every change delivered once, in order.

People sign in with tokens from an OIDC issuer (a local key set here). Keys
carry scopes. The root key only creates workspaces. Events are read by cursor
(with a long poll), as a stream, and as signed webhooks that are retried, in
order, until the receiver takes them.
"""
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kl_support as ks  # noqa: E402
import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from kl import events  # noqa: E402
from kl.api import create_app  # noqa: E402
from kl.client import Client, KLError  # noqa: E402

ISSUER, AUDIENCE = "https://login.example.com", "kl-api"
PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(PRIVATE.public_key()))
JWKS = json.dumps({"keys": [{**JWK, "kid": "k1", "use": "sig", "alg": "RS256"}]})


def token(sub, email, aud=AUDIENCE, exp=3600, iss=ISSUER):
    now = int(time.time())
    return jwt.encode({"iss": iss, "aud": aud, "sub": sub, "email": email, "iat": now, "exp": now + exp},
                      PRIVATE, algorithm="RS256", headers={"kid": "k1"})


class Auth(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc = ks.make_service(cls.tmp, root_key="root-secret", oidc_issuer=ISSUER, oidc_audience=AUDIENCE,
                                  oidc_jwks=JWKS)
        cls.http = TestClient(create_app(cls.svc, mcp=False))
        cls.boot, cls.admin_p = ks.workspace(cls.svc)
        cls.admin = Client("http://testserver", cls.boot["key"], http=cls.http)

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def as_person(self, tok, ws="acme"):
        return Client("http://testserver", tok, workspace=ws, http=self.http)

    def test_a_person_signs_in_with_the_issuers_token_once_an_admin_has_added_them(self):
        tok = token("sub-maria", "maria@acme.example")
        with self.assertRaises(KLError) as e:
            self.as_person(tok).whoami()
        self.assertEqual(e.exception.status, 403)
        self.admin.add_member("maria@acme.example", "Maria", "approver")
        me = self.as_person(tok).whoami()
        self.assertEqual((me["kind"], me["role"], me["name"]), ("user", "approver", "Maria"))
        self.assertIn("review:approve", me["scopes"])

    def test_a_token_for_another_audience_or_expired_or_forged_is_refused(self):
        self.admin.add_member("olu@acme.example", "Olu", "viewer")
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "email": "olu@acme.example",
                             "exp": int(time.time()) + 60}, other, algorithm="RS256", headers={"kid": "k1"})
        for tok in (token("s", "olu@acme.example", aud="someone-else"), token("s", "olu@acme.example", exp=-10),
                    token("s", "olu@acme.example", iss="https://evil.example"), forged):
            with self.subTest(tok=tok[:20]):
                with self.assertRaises(KLError) as e:
                    self.as_person(tok).whoami()
                self.assertEqual(e.exception.status, 401)

    def test_a_person_says_which_workspace(self):
        with self.assertRaises(KLError) as e:
            Client("http://testserver", token("s", "x@acme.example"), http=self.http).whoami()
        self.assertEqual(e.exception.status, 401)
        self.assertIn("KL-Workspace", str(e.exception))

    def test_roles_decide_what_a_person_may_do(self):
        _, key = ks.person(self.svc, self.admin_p, "vic@acme.example", "Vic Viewer", "viewer")
        viewer = Client("http://testserver", key, http=self.http)
        viewer.projects()
        with self.assertRaises(KLError) as e:
            viewer.create_project(id="nope", title="Nope", description="d")
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(KLError):
            viewer.ingest("x.md", text="x")

    def test_only_the_root_key_creates_workspaces(self):
        root = Client("http://testserver", "root-secret", http=self.http)
        ws = root._req("POST", "/v1/workspaces", {"slug": "initech", "name": "Initech"})
        self.assertEqual(ws["slug"], "initech")
        with self.assertRaises(KLError) as e:
            self.admin._req("POST", "/v1/workspaces", {"slug": "other", "name": "Other"})
        self.assertEqual(e.exception.status, 403)

    def test_a_revoked_key_stops_working(self):
        m = self.svc.add_member(self.admin_p, "tmp@acme.example", "Temp", "editor")
        issued = self.svc.create_user_key(self.admin_p, "temp key", user_id=m["user_id"])
        c = Client("http://testserver", issued["key"], http=self.http)
        c.whoami()
        self.admin._req("DELETE", f"/v1/keys/{issued['key_id']}")
        with self.assertRaises(KLError) as e:
            c.whoami()
        self.assertEqual(e.exception.status, 401)

    def test_errors_are_problems(self):
        r = self.http.get("/v1/projects/nope", headers=self.admin.headers)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.headers["content-type"], "application/problem+json")
        self.assertEqual(set(r.json()) >= {"type", "title", "status", "detail"}, True)
        self.assertEqual(self.http.get("/v1/projects").status_code, 401)


class Receiver(BaseHTTPRequestHandler):
    got, fail = [], {"n": 0}

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if Receiver.fail["n"] > 0:
            Receiver.fail["n"] -= 1
            self.send_response(500)
            self.end_headers()
            return
        Receiver.got.append((dict(self.headers), body))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


class Events(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.svc = ks.make_service(cls.tmp)
        cls.http = TestClient(create_app(cls.svc, mcp=False))
        cls.boot, cls.admin_p = ks.workspace(cls.svc)
        cls.admin = Client("http://testserver", cls.boot["key"], http=cls.http)
        cls.server = HTTPServer(("127.0.0.1", 0), Receiver)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.hook_url = f"http://127.0.0.1:{cls.server.server_address[1]}/hook"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.svc.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_events_come_in_order_by_cursor_and_type(self):
        start = self.admin.events(limit=500)["next_after"]
        self.admin.ingest("org-chart.md", text=(ks.CORPUS / "org-chart.md").read_text(encoding="utf-8"))
        page = self.admin.events(after=start)
        self.assertIn("source.ingested", [e["type"] for e in page["items"]])
        seqs = [e["seq"] for e in page["items"]]
        self.assertEqual(seqs, sorted(seqs))
        only = self.admin.events(after=start, types=["job.done"])["items"]
        self.assertTrue(only and all(e["type"] == "job.done" for e in only))
        self.assertEqual(self.admin.events(after=page["next_after"])["items"], [])

    def test_a_long_poll_returns_as_soon_as_something_happens(self):
        after = self.admin.events(limit=500)["next_after"]
        threading.Timer(0.5, lambda: self.svc.create_project(self.admin_p, {
            "id": "poll", "title": "Poll", "description": "d"})).start()
        t0 = time.time()
        page = self.admin.events(after=after, wait=10)
        self.assertLess(time.time() - t0, 5)
        self.assertEqual(page["items"][0]["type"], "change_request.opened")

    def test_webhooks_are_signed_and_retried_in_order_until_delivered(self):
        hook = self.admin.create_webhook(self.hook_url, ["change_request.opened"])
        Receiver.got.clear()
        Receiver.fail["n"] = 1  # the first attempt fails
        for n in (1, 2):
            self.svc.create_project(self.admin_p, {"id": f"hooked-{n}", "title": f"Hooked {n}", "description": "d"})
        first = self.svc.deliver_webhooks()
        self.assertEqual((first["sent"], first["failed"]), (0, 1))
        self.assertEqual(self.admin._req("GET", "/v1/webhooks")[-1]["failures"], 1)
        second = self.svc.deliver_webhooks()
        self.assertEqual(second["sent"], 2)
        bodies = [json.loads(b) for _, b in Receiver.got]
        self.assertEqual([b["data"]["title"] for b in bodies], ["Create project hooked-1", "Create project hooked-2"])
        for headers, body in Receiver.got:
            self.assertTrue(events.verify(hook["secret"], body, headers["KL-Signature"]))
            self.assertFalse(events.verify("wrong", body, headers["KL-Signature"]))
        self.assertEqual(self.svc.deliver_webhooks()["sent"], 0)  # nothing twice

    def test_the_stream_sends_server_sent_events(self):
        after = self.admin.events(limit=500)["next_after"]
        self.svc.create_project(self.admin_p, {"id": "streamed", "title": "Streamed", "description": "d"})
        with self.http.stream("GET", f"/v1/events/stream?after={after}&max_events=1", headers=self.admin.headers) as r:
            self.assertEqual(r.headers["content-type"].split(";")[0], "text/event-stream")
            lines = []
            for line in r.iter_lines():
                lines.append(line)
                if line.startswith("data:"):
                    break
        self.assertIn("event: change_request.opened", lines)
        self.assertEqual(json.loads(lines[-1][5:])["data"]["title"], "Create project streamed")


if __name__ == "__main__":
    unittest.main()
