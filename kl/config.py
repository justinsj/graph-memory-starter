"""Settings, from the environment (KL_*) or passed in."""
import os
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = ""          # sqlite:///path or postgresql+psycopg://user@host/db; default: SQLite in data_dir
    data_dir: Path = Path(".kl-data")  # blobs and each workspace's read model
    public_url: str = "http://localhost:8080"  # what run briefs and leases tell agents to call
    lease_seconds: int = 300        # a run's lease, and its token, last this long past the last renewal
    root_key: str = ""              # may create workspaces (KL_ROOT_KEY); empty: only the CLI can
    oidc_issuer: str = ""           # people sign in with tokens from this issuer
    oidc_audience: str = ""
    oidc_jwks: str = ""             # a JWKS URL, or the JWKS JSON itself
    extractor: str = "none"         # none | claude-cli[:model]: who turns a document into facts
    jobs_inline: bool = True        # run ingestion jobs inside the request (False: a background thread)
    timezone: str = "UTC"           # whose "today": dates on records, and what "as of today" means
    max_upload_bytes: int = 20_000_000
    near_duplicate: float = 0.9     # Jaccard similarity at or above which two documents are near duplicates
    research_before_review: bool = True  # an input's thesis and numbers are researched when its change request
                                    # opens, so the reviewer sees the impact; False: after the project is approved
    thesis_call: str = "parallel"   # parallel: the change set and the thesis in two calls at once (the fastest);
                                    # merged: both in one call (a little cheaper); separate: the thesis after the
                                    # change set, from the proposed project
    graph_updates: str = "deferred"  # deferred: turning an input into a project never rebuilds the graph; what it
                                    # changes is saved as a pending diff (pending-diff.jsonl), applied by the next
                                    # read that needs it or projector.apply_pending(); immediate: rebuilt when next read
    preload_note: bool = True       # tell a model call that what it is given is all there is, so it answers at once:
                                    # only when nothing was left out (every project, every figure the graph holds)
    defaults: dict = field(default_factory=lambda: {
        "self_approval": True,       # a proposer may approve their own request (one approval applies a request)
        "review_extractions": False,  # facts from documents apply once their quotes check out
        "near_duplicates": "link",   # link | ingest | review
        "max_concurrent_runs": 50,
        "max_storage_bytes": 5_000_000_000,
        "impact_research": True,     # a new project gets a draft thesis and its numbers researched, for review
        "unit_values": {},           # what one unit of impact is worth, e.g. {"hours a year": 45}: ranks in money
        "currency": "GBP",
    })

    def with_(self, **kw) -> "Settings":
        return replace(self, **kw)

    @property
    def url(self) -> str:
        return self.database_url or f"sqlite:///{(Path(self.data_dir) / 'kl.db').as_posix()}"


def from_env(**overrides) -> Settings:
    env = os.environ.get
    values = {
        "database_url": env("KL_DATABASE_URL", ""),
        "data_dir": Path(env("KL_DATA_DIR", ".kl-data")),
        "public_url": env("KL_PUBLIC_URL", "http://localhost:8080"),
        "lease_seconds": int(env("KL_LEASE_SECONDS", "300")),
        "root_key": env("KL_ROOT_KEY", ""),
        "oidc_issuer": env("KL_OIDC_ISSUER", ""),
        "oidc_audience": env("KL_OIDC_AUDIENCE", ""),
        "oidc_jwks": env("KL_OIDC_JWKS", ""),
        "extractor": env("KL_EXTRACTOR", "none"),
        "jobs_inline": env("KL_JOBS_INLINE", "1") not in ("0", "false", "no"),
        "timezone": env("KL_TIMEZONE", "UTC"),
        "research_before_review": env("KL_RESEARCH_BEFORE_REVIEW", "1") not in ("0", "false", "no"),
        "thesis_call": env("KL_THESIS_CALL", "parallel"),
        "graph_updates": env("KL_GRAPH_UPDATES", "deferred"),
        "preload_note": env("KL_PRELOAD_NOTE", "1") not in ("0", "false", "no"),
    }
    values.update(overrides)
    return Settings(**values)
