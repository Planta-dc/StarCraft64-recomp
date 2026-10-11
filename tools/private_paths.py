"""Shared private-data boundary for authored tools.

Game-derived output must stay under the ignored repository ``local/`` tree, and
packages must not carry private inputs. Keep these rules in one place so tools,
the APK audit and ``.gitignore`` do not drift apart.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Private suffixes no APK member may use: ROM dumps, saves/states and signing
# keys (all ignored by ``.gitignore``) plus game-derived C and static objects.
# Suffixes that legitimate packages contain (``.so``, ``.png``, ``.bin``) are
# deliberately absent; content checks such as ROM magic cover renamed data.
ROM_SUFFIXES = frozenset({'.z64', '.v64', '.n64', '.rom'})
SAVE_SUFFIXES = frozenset({'.sav', '.sra', '.eep', '.fla', '.mpk', '.state'})
SIGNING_KEY_SUFFIXES = frozenset({'.keystore', '.jks', '.p12', '.pk8', '.pem'})
DERIVED_CODE_SUFFIXES = frozenset({'.c', '.a', '.o', '.obj', '.lib'})
PACKAGE_FORBIDDEN_SUFFIXES = ROM_SUFFIXES | SAVE_SUFFIXES | SIGNING_KEY_SUFFIXES | DERIVED_CODE_SUFFIXES


class PrivatePathError(ValueError):
    """A private output escaped the ignored local/ tree or would overwrite data."""


def require_local(path: Path, *, new: bool = False, root: Path = ROOT, what: str = 'Output') -> Path:
    """Return ``path`` resolved, requiring it under ``root/local`` (and absent if ``new``)."""
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve() / 'local'):
        raise PrivatePathError(f'{what} must stay under ignored local/: {path}')
    if new and (resolved.exists() or resolved.is_symlink()):
        raise PrivatePathError(f'{what} must be new; refusing to reuse {path}')
    return resolved


def require_local_or(fail: Callable[[str], object], path: Path, **kwargs) -> Path:
    """``require_local`` for command-line tools: report a violation through ``fail``.

    Pass ``sys.exit`` or ``argparse.ArgumentParser.error``; both end the process.
    """
    try:
        return require_local(path, **kwargs)
    except PrivatePathError as error:
        fail(str(error))
        raise
