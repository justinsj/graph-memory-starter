"""Who is asking, what they may do, and the plumbing every operation shares.

Four kinds of caller:
- person  (kind "user"): signed in with an OIDC token, or holding a personal
  API key; their role in the workspace decides what they may do.
- system  (kind "service"): a service account's API key, with the scopes it
  was given. It can propose and read, never approve.
- run     (kind "run"): an agent holding a run token. It may read the
  workspace's context and write to its own run, for as long as the lease lives.
- root: the operator's key, which only creates workspaces.
"""
import json
import threading
from dataclasses import dataclass, field

import sqlalchemy as sa

from . import db as t
from . import errors, ids

ROLE_SCOPES = {
    "viewer": {"read", "context:read"},
    "editor": {"read", "context:read", "sources:write", "projects:propose", "plans:propose"},
    "approver": {"read", "context:read", "sources:write", "projects:propose", "plans:propose", "review:approve",
                 "questions:answer"},
    "admin": {"read", "context:read", "sources:write", "projects:propose", "plans:propose", "review:approve",
              "questions:answer", "runs:lease", "webhooks:manage", "admin"},
}
SERVICE_SCOPES = {"read", "context:read", "sources:write", "projects:propose", "plans:propose", "runs:lease",
                  "webhooks:manage"}  # never review:approve: only people approve
RUN_SCOPES = {"read", "context:read", "run"}  # reads the workspace; writes only to its own run


@dataclass(frozen=True)
class Principal:
    kind: str  # user | service | run | root
    id: str
    workspace_id: str = None
    name: str = ""
    role: str = None
    scopes: frozenset = field(default_factory=frozenset)
    run_id: str = None
    secret: str = field(default=None, repr=False, compare=False)  # a run's own token, kept only to redact it

    def can(self, scope: str) -> bool:
        return scope in self.scopes

    def need(self, scope: str) -> None:
        if not self.can(scope):
            raise errors.Forbidden(f"this {self.kind} may not do that: it needs the {scope!r} permission")

    @property
    def is_person(self) -> bool:
        return self.kind == "user"

    @property
    def label(self) -> str:
        return f"{self.name} ({self.kind} {self.id})"


class CoreMixin:
    """Shared plumbing: events, the change log, the version counter, settings."""

    def emit(self, c, ws: str, type_: str, data: dict) -> None:
        c.execute(t.outbox.insert().values(workspace_id=ws, type=type_, data=data, created=self.clock.stamp()))
        self._wake()

    def _wake(self):
        cond = getattr(self, "_events_cond", None)
        if cond is not None:
            with cond:
                cond.notify_all()

    def bump(self, c, ws: str) -> None:
        """The graph must be rebuilt: something it shows has changed."""
        c.execute(t.workspaces.update().where(t.workspaces.c.id == ws)
                  .values(state_version=t.workspaces.c.state_version + 1))

    def log(self, c, ws: str, kind: str, data: dict, actor: str, cr_id: str = None) -> None:
        c.execute(t.change_log.insert().values(workspace_id=ws, cr_id=cr_id, kind=kind, data=data, actor=actor,
                                               at=self.clock.stamp()))

    def ws_settings(self, c, ws: str) -> dict:
        row = c.execute(sa.select(t.workspaces.c.settings).where(t.workspaces.c.id == ws)).scalar_one()
        return {**self.settings.defaults, **(row or {})}

    def workspace_row(self, c, ws: str):
        row = c.execute(sa.select(t.workspaces).where(t.workspaces.c.id == ws)).mappings().first()
        if not row:
            raise errors.NotFound(f"no workspace {ws}")
        return row


class AdminMixin:
    """Workspaces, people, service accounts and keys."""

    def create_workspace(self, p: Principal, slug: str, name: str, settings: dict = None) -> dict:
        if p.kind != "root":
            raise errors.Forbidden("only the operator's root key creates workspaces")
        ws = ids.new("ws")
        with self.db.tx(ws, system=True) as c:
            if c.execute(sa.select(t.workspaces.c.id).where(t.workspaces.c.slug == slug)).first():
                raise errors.Conflict(f"workspace {slug} already exists")
            c.execute(t.workspaces.insert().values(id=ws, slug=slug, name=name, settings=settings or {},
                                                   state_version=0, cr_counter=0, created=self.clock.stamp()))
        return self.get_workspace(ws)

    def get_workspace(self, ws: str) -> dict:
        with self.db.tx(ws) as c:
            row = self.workspace_row(c, ws)
            return {"id": row["id"], "slug": row["slug"], "name": row["name"], "created": row["created"],
                    "settings": {**self.settings.defaults, **(row["settings"] or {})}}

    def update_settings(self, p: Principal, changes: dict) -> dict:
        p.need("admin")
        allowed = set(self.settings.defaults)
        bad = sorted(set(changes) - allowed)
        if bad:
            raise errors.Invalid(f"unknown settings: {', '.join(bad)}", problems=[f"known: {sorted(allowed)}"])
        with self.db.tx(p.workspace_id) as c:
            row = self.workspace_row(c, p.workspace_id)
            c.execute(t.workspaces.update().where(t.workspaces.c.id == p.workspace_id)
                      .values(settings={**(row["settings"] or {}), **changes}))
            self.log(c, p.workspace_id, "settings", changes, p.label)
        return self.get_workspace(p.workspace_id)

    def add_member(self, p: Principal, email: str, name: str, role: str, ws: str = None) -> dict:
        ws = ws or p.workspace_id
        if p.kind != "root":
            p.need("admin")
        if role not in ROLE_SCOPES:
            raise errors.Invalid(f"role must be one of {sorted(ROLE_SCOPES)}")
        with self.db.tx(ws, system=True) as c:
            user = c.execute(sa.select(t.users).where(t.users.c.email == email.lower())).mappings().first()
            if not user:
                uid = ids.new("usr")
                c.execute(t.users.insert().values(id=uid, issuer="", subject="", email=email.lower(), name=name,
                                                  created=self.clock.stamp()))
            else:
                uid = user["id"]
            c.execute(t.members.delete().where(t.members.c.workspace_id == ws, t.members.c.user_id == uid))
            c.execute(t.members.insert().values(workspace_id=ws, user_id=uid, role=role, created=self.clock.stamp()))
            self.log(c, ws, "member", {"user": uid, "email": email, "role": role}, p.label)
        return {"user_id": uid, "email": email.lower(), "name": name, "role": role}

    def list_members(self, p: Principal) -> list:
        p.need("read")
        with self.db.tx(p.workspace_id, system=True) as c:
            rows = c.execute(sa.select(t.members, t.users.c.email, t.users.c.name).join(
                t.users, t.users.c.id == t.members.c.user_id).where(t.members.c.workspace_id == p.workspace_id)
            ).mappings().all()
        return [{"user_id": r["user_id"], "email": r["email"], "name": r["name"], "role": r["role"]} for r in rows]

    def create_service_account(self, p: Principal, name: str, scopes: list) -> dict:
        if p.kind != "root":
            p.need("admin")
        bad = sorted(set(scopes) - SERVICE_SCOPES)
        if bad:
            raise errors.Invalid(f"a service account cannot have {', '.join(bad)}",
                                 problems=["only people approve change requests" if "review:approve" in bad else
                                           f"allowed: {sorted(SERVICE_SCOPES)}"])
        sid = ids.new("svc")
        with self.db.tx(p.workspace_id) as c:
            c.execute(t.service_accounts.insert().values(id=sid, workspace_id=p.workspace_id, name=name,
                                                         created=self.clock.stamp()))
        key = self._issue_key(p.workspace_id, "service", sid, f"{name} key", scopes)
        return {"id": sid, "name": name, "scopes": sorted(scopes), **key}

    def create_user_key(self, p: Principal, name: str, scopes: list = None, user_id: str = None, ws: str = None) -> dict:
        ws = ws or p.workspace_id
        target = user_id or p.id
        if p.kind == "root":
            pass
        elif target != p.id:
            p.need("admin")
        elif not p.is_person:
            raise errors.Forbidden("only people have personal keys")
        with self.db.tx(ws, system=True) as c:
            role = c.execute(sa.select(t.members.c.role).where(t.members.c.workspace_id == ws,
                                                               t.members.c.user_id == target)).scalar()
        if role is None:
            raise errors.NotFound(f"{target} is not a member of this workspace")
        scopes = sorted(set(scopes or ROLE_SCOPES[role]) & ROLE_SCOPES[role])
        return self._issue_key(ws, "user", target, name, scopes)

    def _issue_key(self, ws, kind, pid, name, scopes) -> dict:
        secret = ids.token("kl")
        kid = ids.new("key")
        with self.db.tx(ws, system=True) as c:
            c.execute(t.api_keys.insert().values(id=kid, workspace_id=ws, principal_kind=kind, principal_id=pid,
                                                 name=name, hash=ids.sha256(secret), scopes=sorted(scopes),
                                                 created=self.clock.stamp()))
        return {"key_id": kid, "key": secret, "scopes": sorted(scopes),
                "note": "shown once: store it now; only its hash is kept"}

    def revoke_key(self, p: Principal, key_id: str) -> dict:
        p.need("admin")
        with self.db.tx(p.workspace_id) as c:
            n = c.execute(t.api_keys.update().where(t.api_keys.c.id == key_id,
                                                    t.api_keys.c.workspace_id == p.workspace_id)
                          .values(revoked_at=self.clock.stamp())).rowcount
        if not n:
            raise errors.NotFound(f"no key {key_id}")
        return {"key_id": key_id, "revoked": True}


class AuthMixin:
    """From a request's Authorization header to a Principal."""

    def authenticate(self, authorization: str, workspace: str = None) -> Principal:
        if not authorization:
            raise errors.Unauthorized("send Authorization: Bearer <key or token>")
        scheme, _, cred = authorization.partition(" ")
        if scheme.lower() != "bearer" or not cred:
            raise errors.Unauthorized("use the Bearer scheme")
        cred = cred.strip()
        if self.settings.root_key and ids.same(cred, self.settings.root_key):
            return Principal("root", "root", None, "operator", None, frozenset({"root"}))
        if cred.startswith("klr_"):
            return self._run_principal(cred)
        if cred.startswith("kl_"):
            return self._key_principal(cred)
        if cred.count(".") == 2:
            return self._oidc_principal(cred, workspace)
        raise errors.Unauthorized("that is not a key or token this service issued or trusts")

    def _key_principal(self, secret: str) -> Principal:
        with self.db.tx(system=True) as c:
            k = c.execute(sa.select(t.api_keys).where(t.api_keys.c.hash == ids.sha256(secret))).mappings().first()
            if not k or k["revoked_at"]:
                raise errors.Unauthorized("unknown or revoked key")
            if k["principal_kind"] == "service":
                sa_row = c.execute(sa.select(t.service_accounts).where(
                    t.service_accounts.c.id == k["principal_id"])).mappings().first()
                return Principal("service", k["principal_id"], k["workspace_id"], sa_row["name"] if sa_row else "service",
                                 "service", frozenset(set(k["scopes"]) & SERVICE_SCOPES))
            user = c.execute(sa.select(t.users).where(t.users.c.id == k["principal_id"])).mappings().first()
            role = c.execute(sa.select(t.members.c.role).where(t.members.c.workspace_id == k["workspace_id"],
                                                               t.members.c.user_id == k["principal_id"])).scalar()
        if not user or not role:
            raise errors.Unauthorized("the key's owner is no longer a member")
        return Principal("user", user["id"], k["workspace_id"], user["name"], role,
                         frozenset(set(k["scopes"]) & ROLE_SCOPES[role]))

    def _run_principal(self, token: str) -> Principal:
        with self.db.tx(system=True) as c:
            r = c.execute(sa.select(t.runs).where(t.runs.c.token_hash == ids.sha256(token))).mappings().first()
        if not r:
            raise errors.Unauthorized("unknown run token")
        if r["state"] in ("succeeded", "failed", "lost", "cancelled"):
            ended = ids.parse(r["ended"]).timestamp() if r["ended"] else 0
            if r["state"] in ("succeeded", "failed") and self.clock.epoch() - ended <= self.settings.lease_seconds:
                # a retried complete or fail still gets its first answer; nothing else works any more
                return Principal("run", r["id"], r["workspace_id"], f"run {r['id']} (ended)", "run",
                                 frozenset({"run"}), r["id"], secret=token)
            raise errors.Unauthorized(f"the run is {r['state']}; its token no longer works")
        if r["state"] != "waiting" and r["lease_expires"] < self.clock.epoch():
            raise errors.Unauthorized("the run's lease has expired, and its token with it")
        return Principal("run", r["id"], r["workspace_id"], f"run {r['id']}", "run", frozenset(RUN_SCOPES), r["id"],
                         secret=token)

    _jwks_cache: dict = {}
    _jwks_lock = threading.Lock()

    def _signing_key(self, token: str):
        import jwt
        src = self.settings.oidc_jwks
        if not src:
            raise errors.Unauthorized("this service does not accept sign-in tokens (no OIDC issuer configured)")
        header = jwt.get_unverified_header(token)
        if src.lstrip().startswith("{"):
            keyset = jwt.PyJWKSet.from_json(src)
            for k in keyset.keys:
                if k.key_id == header.get("kid") or header.get("kid") is None:
                    return k.key
            raise errors.Unauthorized("the token's signing key is not in the issuer's key set")
        with self._jwks_lock:
            client = self._jwks_cache.get(src) or jwt.PyJWKClient(src, cache_keys=True)
            self._jwks_cache[src] = client
        return client.get_signing_key_from_jwt(token).key

    def _oidc_principal(self, token: str, workspace: str) -> Principal:
        import jwt
        try:
            claims = jwt.decode(token, self._signing_key(token), algorithms=["RS256", "ES256"],
                                audience=self.settings.oidc_audience or None, issuer=self.settings.oidc_issuer or None,
                                options={"require": ["exp", "sub"]})
        except errors.Problem:
            raise
        except Exception as e:  # noqa: BLE001  any verification failure is the same answer
            raise errors.Unauthorized(f"the sign-in token did not verify: {e}") from None
        if not workspace:
            raise errors.Unauthorized("say which workspace: send KL-Workspace: <slug>")
        with self.db.tx(system=True) as c:
            wsrow = c.execute(sa.select(t.workspaces).where(t.workspaces.c.slug == workspace)).mappings().first()
            if not wsrow:
                raise errors.NotFound(f"no workspace {workspace}")
            iss, sub = claims.get("iss", ""), claims["sub"]
            email = (claims.get("email") or "").lower()
            user = c.execute(sa.select(t.users).where(t.users.c.issuer == iss, t.users.c.subject == sub)).mappings().first()
            if not user and email:  # first sign-in of a person an admin added by email
                user = c.execute(sa.select(t.users).where(t.users.c.email == email, t.users.c.subject == "")
                                 ).mappings().first()
                if user:
                    c.execute(t.users.update().where(t.users.c.id == user["id"]).values(issuer=iss, subject=sub))
            if not user:
                raise errors.Forbidden("you are not a member of this workspace; ask an admin to add you")
            role = c.execute(sa.select(t.members.c.role).where(t.members.c.workspace_id == wsrow["id"],
                                                               t.members.c.user_id == user["id"])).scalar()
        if not role:
            raise errors.Forbidden("you are not a member of this workspace; ask an admin to add you")
        return Principal("user", user["id"], wsrow["id"], user["name"], role, frozenset(ROLE_SCOPES[role]))


def jsonable(row) -> dict:
    return json.loads(json.dumps(dict(row), default=str))
