"""Private local-file creation and permission diagnostics."""

from __future__ import annotations

import contextlib
import os
import stat
from pathlib import Path
from typing import BinaryIO, Iterator


PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def _require_regular_file(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect runtime file: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"refusing to use a symbolic-link runtime file: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"refusing to use a non-regular runtime file: {path}")


def _require_regular_descriptor(descriptor: int, path: Path) -> None:
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError(f"refusing to use a non-regular runtime file: {path}")


def ensure_private_directory(path: Path) -> bool:
    """Create a private directory without changing an existing directory's policy."""
    if path.is_symlink():
        raise ValueError(f"refusing to use a symbolic-link runtime directory: {path}")
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=PRIVATE_DIRECTORY_MODE)
    if created and os.name == "posix":
        path.chmod(PRIVATE_DIRECTORY_MODE)
    return created


def create_private_file(path: Path, payload: bytes = b"") -> bool:
    """Create one file as 0600 without following a pre-existing symlink."""
    ensure_private_directory(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, PRIVATE_FILE_MODE)
    except FileExistsError:
        _require_regular_file(path)
        return False
    try:
        if os.name == "posix":
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
        if payload:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def open_private_append(path: Path) -> BinaryIO:
    """Open an append-only private file, creating it safely when absent."""
    ensure_private_directory(path.parent)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | nofollow | nonblock,
            PRIVATE_FILE_MODE,
        )
        if os.name == "posix":
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
    except FileExistsError:
        _require_regular_file(path)
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | nofollow | nonblock)
    _require_regular_descriptor(descriptor, path)
    return os.fdopen(descriptor, "ab")


def open_private_lock(path: Path) -> BinaryIO:
    """Open a private read/write lock file without following symlinks."""
    ensure_private_directory(path.parent)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow | nonblock,
            PRIVATE_FILE_MODE,
        )
        if os.name == "posix":
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
    except FileExistsError:
        _require_regular_file(path)
        descriptor = os.open(path, os.O_RDWR | nofollow | nonblock)
    _require_regular_descriptor(descriptor, path)
    return os.fdopen(descriptor, "a+b")


@contextlib.contextmanager
def exclusive_file_lock(handle: BinaryIO) -> Iterator[None]:
    """Hold an interprocess lock for one private lock-file handle.

    POSIX ``flock`` can lock an empty file, while Windows ``msvcrt.locking``
    locks a byte range starting at the current file position.  Keep one byte in
    the lock file and always lock byte zero so both implementations protect the
    same critical section.
    """
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)
    try:
        import fcntl
    except ImportError:  # pragma: no cover - exercised with a simulated Windows module
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def permission_issues(home: Path, files: list[Path]) -> list[str]:
    """Report permissive or symlinked runtime paths without mutating them."""
    if os.name != "posix":
        return []
    issues: list[str] = []
    targets = [(home, PRIVATE_DIRECTORY_MODE), *((path, PRIVATE_FILE_MODE) for path in files)]
    for path, expected in targets:
        try:
            info = path.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(info.st_mode):
            issues.append(f"{path}: symbolic link")
            continue
        actual = stat.S_IMODE(info.st_mode)
        if actual & 0o077:
            issues.append(f"{path}: mode {actual:04o}, expected no group/other access")
        elif path == home and not stat.S_ISDIR(info.st_mode):
            issues.append(f"{path}: runtime home is not a directory")
        elif path != home and not stat.S_ISREG(info.st_mode):
            issues.append(f"{path}: runtime artifact is not a regular file")
        elif actual != expected:
            # Owner-only modes such as 0400 are safe but can make the runtime unusable.
            issues.append(f"{path}: mode {actual:04o}, expected {expected:04o}")
    return issues
