"""The harness2cc configuration: where the user's files live and what a run may change.

The configuration and every file harness2cc writes (decision points, labels, runs, the
library, backups and the ledger) live in the harness2cc home folder, never in this
repository. The home folder is `~/.claude/harness2cc/` unless `HARNESS2CC_HOME` names
another one, which is how the tests keep away from the real one.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

HOME_ENVIRONMENT_VARIABLE = "HARNESS2CC_HOME"
CONFIG_FILE_NAME = "config.json"
MODEL_ROLES: tuple[str, ...] = ("executor", "editor", "grader")
CAP_NAMES: tuple[str, ...] = (
    "max_references", "max_k", "library_entries_per_domain", "claude_md_growth_characters",
)
SOURCE_MAP_FIELDS: tuple[str, ...] = ("live", "source", "guide_step")


class ConfigurationError(ValueError):
    """The configuration file is missing, unreadable, or has a missing or invalid key."""


@dataclass(frozen=True)
class SourceMapping:
    """A live harness file that has a source copy in this repository and the install guide."""

    live: str
    source: str
    guide_step: str


@dataclass(frozen=True)
class Harness2ccConfig:
    """The validated configuration. Paths in it are absolute; harness file paths are relative to the workspace."""

    home: Path
    workspace_root: Path
    transcript_roots: tuple[Path, ...]
    editable_files: tuple[str, ...]
    protected_sections: dict[str, tuple[str, ...]]
    protected_files: tuple[str, ...]
    source_map: tuple[SourceMapping, ...]
    client_terms_file: Path
    models: dict[str, str]
    caps: dict[str, int]

    @property
    def decision_points_file(self) -> Path:
        """The JSON-lines file of decision points the last scan found (no answers in it)."""
        return self.home / "decision_points.jsonl"

    @property
    def labels_file(self) -> Path:
        """The JSON-lines file of the user's answers, read only by the grader and `list-references`."""
        return self.home / "labels.jsonl"


def harness2cc_home() -> Path:
    """Return the harness2cc home folder: `HARNESS2CC_HOME` when set, else `~/.claude/harness2cc`.

    Returns:
        The absolute home folder path. It is not created here.
    """
    configured = os.environ.get(HOME_ENVIRONMENT_VARIABLE, "").strip()
    return Path(configured).expanduser().resolve() if configured else (Path.home() / ".claude" / "harness2cc")


def require_key(raw: dict, key: str, expected_type: type, config_path: Path) -> object:
    """Return `raw[key]`, raising when the key is missing or holds the wrong type.

    Args:
        raw: The parsed configuration object.
        key: The key to read.
        expected_type: The JSON type the value must have (str, list, dict or int).
        config_path: The configuration file, named in the error.

    Returns:
        The value.

    Raises:
        ConfigurationError: When the key is missing or its value has another type.
    """
    if key not in raw:
        raise ConfigurationError(f"{config_path}: missing key '{key}'")
    value = raw[key]
    if expected_type is int and isinstance(value, bool) or not isinstance(value, expected_type):
        raise ConfigurationError(
            f"{config_path}: key '{key}' must be a {expected_type.__name__}, got {type(value).__name__}")
    return value


def require_string_list(raw: dict, key: str, config_path: Path) -> tuple[str, ...]:
    """Return `raw[key]` as a tuple of non-empty strings, raising when it is anything else.

    Args:
        raw: The parsed configuration object.
        key: The key to read.
        config_path: The configuration file, named in the error.

    Returns:
        The strings, in order.

    Raises:
        ConfigurationError: When the key is missing, is not a list, or holds a non-string or empty item.
    """
    values = require_key(raw, key, list, config_path)
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"{config_path}: key '{key}' item {index} must be a non-empty string")
    return tuple(values)


def require_existing_directory(path_text: str, key: str, config_path: Path) -> Path:
    """Return a configured folder path, raising when the folder does not exist.

    Args:
        path_text: The path as written in the configuration.
        key: The key it came from, named in the error.
        config_path: The configuration file, named in the error.

    Returns:
        The absolute folder path.

    Raises:
        ConfigurationError: When the folder does not exist.
    """
    path = Path(path_text).expanduser()
    if not path.is_dir():
        raise ConfigurationError(f"{config_path}: key '{key}' names a folder that does not exist: {path}")
    return path.resolve()


def load_config(home: Path | None = None) -> Harness2ccConfig:
    """Read and validate `config.json` in the harness2cc home folder.

    Args:
        home: The home folder; `harness2cc_home()` when omitted.

    Returns:
        The validated configuration.

    Raises:
        ConfigurationError: When the file is missing or not JSON, or a key is missing or invalid. The message
            names the file and the key.
    """
    home = (home or harness2cc_home()).resolve()
    config_path = home / CONFIG_FILE_NAME
    if not config_path.is_file():
        raise ConfigurationError(
            f"{config_path} does not exist. Copy harness2cc/config.example.json there and fill in your values.")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigurationError(f"{config_path} is not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{config_path} must hold a JSON object")

    workspace_root = require_existing_directory(
        require_key(raw, "workspace_root", str, config_path), "workspace_root", config_path)
    transcript_roots = tuple(
        require_existing_directory(path_text, "transcript_roots", config_path)
        for path_text in require_string_list(raw, "transcript_roots", config_path))
    if not transcript_roots:
        raise ConfigurationError(f"{config_path}: key 'transcript_roots' must name at least one folder")

    raw_sections = require_key(raw, "protected_sections", dict, config_path)
    protected_sections: dict[str, tuple[str, ...]] = {}
    for file_name, headings in raw_sections.items():
        if not isinstance(headings, list) or not all(isinstance(heading, str) and heading for heading in headings):
            raise ConfigurationError(
                f"{config_path}: key 'protected_sections' entry '{file_name}' must be a list of headings")
        protected_sections[file_name] = tuple(headings)

    source_map: list[SourceMapping] = []
    for index, item in enumerate(require_key(raw, "source_map", list, config_path)):
        if not isinstance(item, dict):
            raise ConfigurationError(f"{config_path}: key 'source_map' item {index} must be an object")
        for field_name in SOURCE_MAP_FIELDS:
            if not isinstance(item.get(field_name), str) or not item[field_name]:
                raise ConfigurationError(
                    f"{config_path}: key 'source_map' item {index} is missing '{field_name}'")
        source_map.append(SourceMapping(item["live"], item["source"], item["guide_step"]))

    client_terms_text = require_key(raw, "client_terms_file", str, config_path)
    client_terms_file = Path(client_terms_text).expanduser()
    if not client_terms_file.is_absolute():
        client_terms_file = home / client_terms_file

    raw_models = require_key(raw, "models", dict, config_path)
    models: dict[str, str] = {}
    for role in MODEL_ROLES:
        if not isinstance(raw_models.get(role), str) or not raw_models[role].strip():
            raise ConfigurationError(f"{config_path}: key 'models' is missing '{role}'")
        models[role] = raw_models[role]

    raw_caps = require_key(raw, "caps", dict, config_path)
    caps: dict[str, int] = {}
    for cap_name in CAP_NAMES:
        value = raw_caps.get(cap_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigurationError(f"{config_path}: key 'caps' is missing '{cap_name}' or it is not a positive integer")
        caps[cap_name] = value

    return Harness2ccConfig(
        home=home,
        workspace_root=workspace_root,
        transcript_roots=transcript_roots,
        editable_files=require_string_list(raw, "editable_files", config_path),
        protected_sections=protected_sections,
        protected_files=require_string_list(raw, "protected_files", config_path),
        source_map=tuple(source_map),
        client_terms_file=client_terms_file,
        models=models,
        caps=caps,
    )
