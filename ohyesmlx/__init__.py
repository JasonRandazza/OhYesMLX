"""OhYesMLX: Honest benchmarks for local LLM serving on Apple Silicon."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "app_support_dir",
    "writable_root",
    "ensure_app_support",
    "stderr_json",
]

# The app's own directory holds engine venvs, the fetch ledger, quickbench summaries and the
# pinned Osaurus baseline when the package is installed. Nothing in it belongs to another user.
APP_SUPPORT_MODE = 0o700


def app_support_dir(home=None) -> Path:
    """The app's directory for *home* (default: this user's home): ``~/Library/Application Support/OhYesMLX``."""
    base = Path(home) if home is not None else Path.home()
    return base / "Library" / "Application Support" / "OhYesMLX"


def _repo_root() -> Path:
    """The directory the installed package sits in (the checkout, when there is one)."""
    return Path(__file__).resolve().parents[1]


def _is_checkout() -> bool:
    """Whether this package runs from a git checkout, asked as a small function tests can patch."""
    return (_repo_root() / ".git").exists()


def writable_root() -> Path:
    """The one directory the app may write in: the checkout, else Application Support.

    A checkout keeps today's paths -- ``<repo>/config/`` and ``<repo>/results/logs`` -- so no
    harness run, canary or published table moves. An installed copy has no writable package
    tree, so everything that used to land beside the package lands under Application Support
    instead.
    """
    root = _repo_root()
    return root if _is_checkout() else app_support_dir()


def ensure_app_support(home=None) -> Path:
    """Create the Application Support directory 0700, or tighten an existing one to 0700."""
    path = app_support_dir(home)
    # mkdir's mode is filtered by the umask, so the chmod is what makes the mode a guarantee
    # rather than a request -- for a directory this call created and for one already there.
    path.mkdir(parents=True, exist_ok=True, mode=APP_SUPPORT_MODE)
    path.chmod(APP_SUPPORT_MODE)
    return path


def stderr_json(payload: dict) -> None:
    """Write one JSON line to stderr, flushed: the one definition of a machine-readable line."""
    print(json.dumps(payload), file=sys.stderr, flush=True)
