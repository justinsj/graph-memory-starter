"""The service: every operation, whichever door it comes through (REST, MCP, the SDK)."""
import threading
from pathlib import Path

from . import extractors
from .blobs import LocalBlobs
from .config import Settings, from_env
from .context import ContextMixin
from .core import AdminMixin, AuthMixin, CoreMixin, Principal
from .db import Database
from .events import EventsMixin
from .ids import Clock
from .plans import PlansMixin
from .projection import Projector
from .projects import ProjectsMixin
from .review import ReviewMixin
from .runs import RunsMixin
from .sources import SourcesMixin


class Service(CoreMixin, AdminMixin, AuthMixin, SourcesMixin, ReviewMixin, ProjectsMixin, PlansMixin, RunsMixin,
              ContextMixin, EventsMixin):

    def __init__(self, settings: Settings = None, extractor=None, create: bool = True, app_role: str = None):
        self.settings = settings or from_env()
        Path(self.settings.data_dir).mkdir(parents=True, exist_ok=True)
        self.db = Database(self.settings.url)
        if create:
            self.db.create(app_role=app_role)
        self.blobs = LocalBlobs(Path(self.settings.data_dir) / "blobs")
        self.clock = Clock(self.settings.timezone)
        self.projector = Projector(self.db, self.blobs, self.settings.data_dir, self.clock)
        self.extractor = extractor or extractors.from_setting(self.settings.extractor)
        self._events_cond = threading.Condition()
        self._tls = threading.local()

    def root(self) -> Principal:
        """The operator, for the CLI and tests."""
        return Principal("root", "root", None, "operator", None, frozenset({"root"}))

    def bootstrap(self, slug: str, name: str, admin_email: str, admin_name: str) -> dict:
        """A workspace, its first admin and the admin's key: what `python -m kl init` prints."""
        ws = self.create_workspace(self.root(), slug, name)
        member = self.add_member(self.root(), admin_email, admin_name, "admin", ws=ws["id"])
        key = self.create_user_key(self.root(), "first admin key", user_id=member["user_id"], ws=ws["id"])
        return {"workspace": ws, "admin": member, **key}

    def close(self):
        self.stop_background()
        self.db.dispose()
