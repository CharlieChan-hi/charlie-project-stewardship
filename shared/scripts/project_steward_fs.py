#!/usr/bin/env python3
"""Secure project-local filesystem and transaction primitives."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import hashlib
import os
import secrets
import stat
import tempfile
import time
from pathlib import Path
from typing import Iterable, Iterator


_SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "id_rsa",
    "id_ed25519",
}


class ProjectPathError(ValueError):
    """Raised when a requested path is unsafe for project-local access."""


class ConcurrentModificationError(RuntimeError):
    """Raised when a file changed after it was inspected."""


@dataclass(frozen=True)
class PreparedWrite:
    """One fully preflighted project-local text replacement request."""

    path: Path
    content: str
    expected_signature: str | None


@dataclass
class _StagedWrite:
    request: PreparedWrite
    relative: Path
    original: bytes | None
    original_mode: int
    new_signature: str
    parent_fd: int
    root_fd: int
    temporary_name: str | None
    temporary_identity: tuple[int, int]
    committed: bool = False


def canonical_root(root: Path) -> Path:
    """Return the canonical project root without requiring it to exist yet."""
    return root.expanduser().resolve(strict=False)


def _absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _project_path_and_relative(root: Path, path: Path) -> tuple[Path, Path]:
    """Map lexical platform aliases such as macOS /var to one canonical root."""
    canonical = canonical_root(root)
    lexical_root = _absolute_without_resolving(root)
    lexical_path = _absolute_without_resolving(path)
    try:
        relative = lexical_path.relative_to(lexical_root)
    except ValueError:
        parent_resolved = lexical_path.parent.resolve(strict=False)
        mapped = parent_resolved / lexical_path.name
        try:
            relative = mapped.relative_to(canonical)
        except ValueError as exc:
            raise ProjectPathError(f"File escapes the project root: {path}") from exc
    candidate = canonical / relative
    safe_project_path(canonical, relative)
    return candidate, relative


def _is_sensitive_part(part: str) -> bool:
    lowered = part.lower()
    return lowered in _SENSITIVE_NAMES or lowered.startswith(".env.")


def safe_project_path(
    root: Path,
    rel_path: str | Path,
    *,
    allow_sensitive: bool = False,
) -> Path:
    """Resolve a relative project path without following writable symlink hops."""
    canonical = canonical_root(root)
    relative = Path(rel_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProjectPathError(f"Path must stay relative to the project root: {rel_path}")
    if not allow_sensitive and any(_is_sensitive_part(part) for part in relative.parts):
        raise ProjectPathError(f"Sensitive path is not readable or writable: {rel_path}")

    candidate = canonical / relative
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(canonical)
    except ValueError as exc:
        raise ProjectPathError(f"Path escapes the project root: {rel_path}") from exc

    current = canonical
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ProjectPathError(f"Refusing symlink path inside project root: {rel_path}")
        if not current.exists():
            break
    return candidate


def _secure_dirfd_available() -> bool:
    """Return whether this runtime can anchor every project mutation to dirfds."""
    required = (os.open, os.stat, os.mkdir, os.unlink, os.rmdir, os.rename)
    return (
        os.name == "posix"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and all(function in os.supports_dir_fd for function in required)
        and os.stat in os.supports_follow_symlinks
    )


def _secure_archive_available() -> bool:
    """Return whether no-replace hard links can support an anchored archive."""
    return (
        _secure_dirfd_available()
        and os.link in os.supports_dir_fd
        and os.link in os.supports_follow_symlinks
    )


def require_mutation_capability(operation: str) -> None:
    """Fail before any lock, directory, or staged-file artifact can be created."""
    if operation not in {"write", "delete", "archive"}:
        raise ValueError(f"Unknown project mutation capability: {operation}")
    if operation == "archive":
        if not _secure_archive_available():
            raise RuntimeError(
                "Secure project archive requires descriptor-anchored unlink and hard-link support"
            )
        return
    if not _secure_dirfd_available():
        if operation == "write":
            raise RuntimeError(
                "Secure project writes require descriptor-anchored mutation support"
            )
        raise RuntimeError(
            "Secure project deletion requires descriptor-anchored unlink support"
        )


def _directory_open_flags() -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _translate_directory_error(path: Path, exc: OSError) -> ProjectPathError:
    if exc.errno in {
        errno.ELOOP,
        errno.EMLINK,
        errno.ENOTDIR,
    }:
        return ProjectPathError(f"Refusing non-directory or symlink path: {path}")
    return ProjectPathError(f"Cannot safely open project directory {path}: {exc}")


def _open_directory_path_fd(directory: Path) -> int:
    """Open one trusted path used only for the filesystem anchor itself."""
    try:
        fd = os.open(directory, _directory_open_flags())
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise _translate_directory_error(directory, exc) from exc
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise ProjectPathError(f"Expected a directory: {directory}")
    return fd


def _open_absolute_directory_fd(directory: Path) -> int:
    """Open an absolute directory one no-follow component at a time."""
    if not directory.is_absolute() or not directory.anchor:
        raise ProjectPathError(f"Expected an absolute project directory: {directory}")
    anchor = Path(directory.anchor)
    anchor_fd = _open_directory_path_fd(anchor)
    if directory == anchor:
        return anchor_fd
    try:
        relative = Path(*directory.parts[1:])
        fd, _created = _open_relative_directory(
            anchor_fd,
            relative,
            create=False,
        )
        return fd
    finally:
        os.close(anchor_fd)


def _open_or_create_absolute_directory_fd(
    directory: Path,
) -> tuple[int, list[Path]]:
    """Open an absolute directory, securely creating missing components."""
    if not directory.is_absolute() or not directory.anchor:
        raise ProjectPathError(f"Expected an absolute project root: {directory}")
    anchor = Path(directory.anchor)
    anchor_fd = _open_directory_path_fd(anchor)
    if directory == anchor:
        return anchor_fd, []
    try:
        relative = Path(*directory.parts[1:])
        fd, created_relative = _open_relative_directory(
            anchor_fd,
            relative,
            create=True,
        )
        return fd, [anchor / item for item in created_relative]
    finally:
        os.close(anchor_fd)


def _validate_relative_path(relative: Path) -> None:
    if relative.is_absolute() or ".." in relative.parts:
        raise ProjectPathError(f"Path must stay relative to the project root: {relative}")


def _open_relative_directory(
    root_fd: int,
    relative: Path,
    *,
    create: bool,
) -> tuple[int, list[Path]]:
    """Walk a relative directory one no-follow component at a time."""
    _validate_relative_path(relative)
    current_fd = os.dup(root_fd)
    created: list[Path] = []
    traversed = Path()
    try:
        for part in relative.parts:
            traversed /= part
            try:
                next_fd = os.open(part, _directory_open_flags(), dir_fd=current_fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o755, dir_fd=current_fd)
                    created.append(traversed)
                except FileExistsError:
                    pass
                try:
                    next_fd = os.open(part, _directory_open_flags(), dir_fd=current_fd)
                except OSError as exc:
                    raise _translate_directory_error(traversed, exc) from exc
            except OSError as exc:
                raise _translate_directory_error(traversed, exc) from exc
            if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                os.close(next_fd)
                raise ProjectPathError(f"Expected a directory: {traversed}")
            os.close(current_fd)
            current_fd = next_fd
        return current_fd, created
    except BaseException:
        os.close(current_fd)
        raise


def _final_name(relative: Path) -> str:
    _validate_relative_path(relative)
    name = relative.name
    if not name or name in {".", ".."} or Path(name).parts != (name,):
        raise ProjectPathError(f"Expected a project-local filename: {relative}")
    return name


def _open_regular_at(parent_fd: int, name: str) -> int:
    """Open one regular final component without following it or blocking on a FIFO."""
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise ProjectPathError(f"Refusing symlink file: {name}") from exc
        raise
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ProjectPathError(f"Expected a regular file: {name}")
    return fd


def _read_regular_snapshot_at(
    parent_fd: int,
    name: str,
) -> tuple[bytes, int, tuple[int, int]] | None:
    """Read bytes, mode, and identity from the same anchored file descriptor."""
    try:
        fd = _open_regular_at(parent_fd, name)
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(fd)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return (
            b"".join(chunks),
            stat.S_IMODE(metadata.st_mode),
            (metadata.st_dev, metadata.st_ino),
        )
    finally:
        os.close(fd)


def _read_regular_at(parent_fd: int, name: str) -> tuple[bytes, int] | None:
    snapshot = _read_regular_snapshot_at(parent_fd, name)
    return None if snapshot is None else (snapshot[0], snapshot[1])


def _signature_at(parent_fd: int, name: str) -> str | None:
    snapshot = _read_regular_at(parent_fd, name)
    return None if snapshot is None else content_signature(snapshot[0])


def _assert_parent_reachable(root_fd: int, relative: Path, parent_fd: int) -> None:
    """Fail if the currently named parent no longer identifies the held directory."""
    try:
        current_fd, _created = _open_relative_directory(
            root_fd,
            relative,
            create=False,
        )
    except (OSError, ProjectPathError) as exc:
        raise ConcurrentModificationError(
            f"Project parent changed while accessing {relative or Path('.')}"
        ) from exc
    try:
        expected = os.fstat(parent_fd)
        current = os.fstat(current_fd)
        if (expected.st_dev, expected.st_ino) != (current.st_dev, current.st_ino):
            raise ConcurrentModificationError(
                f"Project parent changed while accessing {relative or Path('.')}"
            )
    finally:
        os.close(current_fd)


def _parent_chain_identity(root: Path, relative: Path) -> tuple[tuple[int, int], ...]:
    """Best-effort parent identity snapshot for platforms without dirfd support."""
    _validate_relative_path(relative)
    identities: list[tuple[int, int]] = []
    current = canonical_root(root)
    for part in (Path(), *relative.parts):
        if part:
            current /= part
        metadata = current.lstat()
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if current.is_symlink() or attributes & reparse_point:
            raise ProjectPathError(f"Refusing symlink or reparse-point directory: {current}")
        if not stat.S_ISDIR(metadata.st_mode):
            raise ProjectPathError(f"Expected a directory: {current}")
        identities.append((metadata.st_dev, metadata.st_ino))
    return tuple(identities)


@contextmanager
def open_project_regular_file(path: Path, *, root: Path) -> Iterator[object]:
    """Open a project file through an anchored parent descriptor when supported."""
    path, relative = _project_path_and_relative(root, path)
    canonical = canonical_root(root)
    if _secure_dirfd_available():
        root_fd = _open_absolute_directory_fd(canonical)
        parent_fd: int | None = None
        file_fd: int | None = None
        try:
            parent_fd, _created = _open_relative_directory(
                root_fd,
                relative.parent,
                create=False,
            )
            _assert_parent_reachable(root_fd, relative.parent, parent_fd)
            file_fd = _open_regular_at(parent_fd, _final_name(relative))
            handle = os.fdopen(file_fd, "rb")
            file_fd = None
            with handle:
                yield handle
            _assert_parent_reachable(root_fd, relative.parent, parent_fd)
        finally:
            if file_fd is not None:
                os.close(file_fd)
            if parent_fd is not None:
                os.close(parent_fd)
            os.close(root_fd)
        return

    before = _parent_chain_identity(canonical, relative.parent)
    fd: int | None = None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ProjectPathError(f"Expected a regular file: {path}")
        try:
            named = path.lstat()
        except FileNotFoundError as exc:
            raise ConcurrentModificationError(
                f"Project file changed while opening {relative}"
            ) from exc
        attributes = getattr(named, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if (
            stat.S_ISLNK(named.st_mode)
            or attributes & reparse_point
            or not stat.S_ISREG(named.st_mode)
        ):
            raise ProjectPathError(f"Refusing symlink or reparse-point file: {path}")
        opened_identity = (opened.st_dev, opened.st_ino)
        named_identity = (named.st_dev, named.st_ino)
        if opened.st_ino == 0 or opened_identity != named_identity:
            raise ConcurrentModificationError(
                f"Project file changed while opening {relative}"
            )
        if before != _parent_chain_identity(canonical, relative.parent):
            raise ConcurrentModificationError(f"Project parent changed while opening {relative}")
        handle = os.fdopen(fd, "rb")
        fd = None
        with handle:
            yield handle
        if before != _parent_chain_identity(canonical, relative.parent):
            raise ConcurrentModificationError(f"Project parent changed while reading {relative}")
    finally:
        if fd is not None:
            os.close(fd)


def content_signature(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular_file_snapshot(
    path: Path,
) -> tuple[bytes, int, tuple[int, int]] | None:
    """Path-based compatibility reader for callers without a project root."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise ProjectPathError(f"Refusing symlink file: {path}") from exc
        raise

    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProjectPathError(f"Expected a regular file: {path}")
        if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
            raise ProjectPathError(f"Refusing symlink file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
            raise ProjectPathError(f"File became a symlink while reading: {path}")
        return (
            b"".join(chunks),
            stat.S_IMODE(metadata.st_mode),
            (metadata.st_dev, metadata.st_ino),
        )
    finally:
        os.close(fd)


def _read_regular_file(path: Path) -> tuple[bytes, int] | None:
    snapshot = _read_regular_file_snapshot(path)
    return None if snapshot is None else (snapshot[0], snapshot[1])


def file_signature(path: Path, *, root: Path | None = None) -> str | None:
    if root is None:
        snapshot = _read_regular_file(path)
        return None if snapshot is None else content_signature(snapshot[0])
    try:
        with open_project_regular_file(path, root=root) as handle:
            return content_signature(handle.read())
    except FileNotFoundError:
        return None


def read_text_safe(path: Path, *, root: Path) -> tuple[str, str | None]:
    """Read a known project artifact and return text plus a conflict token."""
    try:
        with open_project_regular_file(path, root=root) as handle:
            data = handle.read()
    except FileNotFoundError:
        return "", None
    return data.decode("utf-8"), content_signature(data)


def _entry_identity_at(parent_fd: int, name: str) -> tuple[int, int]:
    metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise ProjectPathError(f"Expected a regular file: {name}")
    return metadata.st_dev, metadata.st_ino


def _unlink_at(
    parent_fd: int,
    name: str,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> bool:
    try:
        identity = _entry_identity_at(parent_fd, name)
    except FileNotFoundError:
        return False
    if expected_identity is not None and identity != expected_identity:
        raise ConcurrentModificationError(
            f"Refusing to remove a replacement for staged file {name}"
        )
    os.unlink(name, dir_fd=parent_fd)
    return True


def _replace_at(parent_fd: int, source_name: str, target_name: str) -> None:
    os.rename(
        source_name,
        target_name,
        src_dir_fd=parent_fd,
        dst_dir_fd=parent_fd,
    )


def _link_at(
    source_parent_fd: int,
    source_name: str,
    target_parent_fd: int,
    target_name: str,
) -> None:
    """Create an anchored no-replace hard link without following the source."""
    os.link(
        source_name,
        target_name,
        src_dir_fd=source_parent_fd,
        dst_dir_fd=target_parent_fd,
        follow_symlinks=False,
    )


def _anchored_file_matches(
    parent_fd: int,
    name: str,
    *,
    expected_identity: tuple[int, int],
    expected_signature: str,
) -> bool:
    snapshot = _read_regular_snapshot_at(parent_fd, name)
    if snapshot is None:
        return False
    data, _mode, identity = snapshot
    if identity != expected_identity or content_signature(data) != expected_signature:
        return False
    try:
        return _entry_identity_at(parent_fd, name) == expected_identity
    except (FileNotFoundError, ProjectPathError):
        return False


def _restore_regular_at(
    parent_fd: int,
    name: str,
    *,
    display_path: Path,
    data: bytes,
    mode: int,
    expected_signature: str,
) -> None:
    """Restore missing original bytes without overwriting a concurrent source."""
    current = _read_regular_snapshot_at(parent_fd, name)
    if current is not None:
        if content_signature(current[0]) == expected_signature:
            return
        raise ConcurrentModificationError(
            f"Cannot restore {display_path}; a different source file now exists"
        )

    temporary_name, temporary_identity = _stage_bytes(
        display_path,
        data,
        mode,
        parent_fd=parent_fd,
    )
    try:
        try:
            _link_at(parent_fd, temporary_name, parent_fd, name)
        except FileExistsError:
            current = _read_regular_snapshot_at(parent_fd, name)
            if current is not None and content_signature(current[0]) == expected_signature:
                return
            raise ConcurrentModificationError(
                f"Cannot restore {display_path}; the source path was concurrently recreated"
            )
        if not _unlink_at(
            parent_fd,
            temporary_name,
            expected_identity=temporary_identity,
        ):
            raise ConcurrentModificationError(
                f"Source restoration staging file disappeared for {display_path}"
            )
        temporary_name = None
        _fsync_directory(directory_fd=parent_fd)
        if not _anchored_file_matches(
            parent_fd,
            name,
            expected_identity=temporary_identity,
            expected_signature=expected_signature,
        ):
            raise ConcurrentModificationError(
                f"Restored source verification failed for {display_path}"
            )
    finally:
        if temporary_name is not None:
            _unlink_at(
                parent_fd,
                temporary_name,
                expected_identity=temporary_identity,
            )


def _stage_bytes(
    path: Path,
    data: bytes,
    mode: int,
    *,
    parent_fd: int,
) -> tuple[str, tuple[int, int]]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    for _attempt in range(128):
        name = f".{path.name}.{secrets.token_hex(16)}.tmp"
        try:
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
            break
        except FileExistsError:
            continue
    else:
        raise FileExistsError(f"Could not allocate a staged file for {path}")

    identity = os.fstat(fd).st_dev, os.fstat(fd).st_ino
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ProjectPathError(f"Unsafe staged file: {path.parent / name}")
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise OSError("Short write while staging project file")
            offset += written
        os.fchmod(fd, mode)
        os.fsync(fd)
        return name, identity
    except BaseException:
        os.close(fd)
        fd = -1
        _unlink_at(parent_fd, name, expected_identity=identity)
        raise
    finally:
        if fd >= 0:
            os.close(fd)


def _fsync_directory(*, directory_fd: int) -> None:
    os.fsync(directory_fd)


def _commit_staged(stage: _StagedWrite) -> None:
    """Commit one already-staged file. Kept separate for failure-injection tests."""
    name = _final_name(stage.relative)
    _assert_parent_reachable(stage.root_fd, stage.relative.parent, stage.parent_fd)
    if _signature_at(stage.parent_fd, name) != stage.request.expected_signature:
        raise ConcurrentModificationError(
            f"Concurrent modification detected before replacing {stage.relative}"
        )
    if stage.temporary_name is None:
        raise ConcurrentModificationError(f"Missing staged payload for {stage.relative}")
    if (
        _entry_identity_at(stage.parent_fd, stage.temporary_name)
        != stage.temporary_identity
    ):
        raise ConcurrentModificationError(
            f"Staged payload changed before replacing {stage.relative}"
        )
    _replace_at(stage.parent_fd, stage.temporary_name, name)
    stage.temporary_name = None
    stage.committed = True
    _fsync_directory(directory_fd=stage.parent_fd)
    _assert_parent_reachable(stage.root_fd, stage.relative.parent, stage.parent_fd)


def _rollback_committed(stage: _StagedWrite) -> None:
    name = _final_name(stage.relative)
    current_signature = _signature_at(stage.parent_fd, name)
    if current_signature != stage.new_signature:
        raise ConcurrentModificationError(
            f"Cannot roll back {stage.relative}; the committed file changed again"
        )
    if stage.original is None:
        if not _unlink_at(stage.parent_fd, name):
            raise ConcurrentModificationError(
                f"Cannot roll back {stage.relative}; the committed file disappeared"
            )
        _fsync_directory(directory_fd=stage.parent_fd)
        stage.committed = False
        return
    replacement_name, replacement_identity = _stage_bytes(
        stage.request.path,
        stage.original,
        stage.original_mode,
        parent_fd=stage.parent_fd,
    )
    try:
        _replace_at(stage.parent_fd, replacement_name, name)
        replacement_name = None
        _fsync_directory(directory_fd=stage.parent_fd)
        stage.committed = False
    finally:
        if replacement_name is not None:
            _unlink_at(
                stage.parent_fd,
                replacement_name,
                expected_identity=replacement_identity,
            )


def _remove_created_directory(root_fd: int, relative: Path) -> None:
    if not relative.parts:
        return
    parent_fd, _created = _open_relative_directory(
        root_fd,
        relative.parent,
        create=False,
    )
    try:
        os.rmdir(_final_name(relative), dir_fd=parent_fd)
        _fsync_directory(directory_fd=parent_fd)
    finally:
        os.close(parent_fd)


def _remove_created_absolute_directories(directories: list[Path]) -> None:
    for directory in sorted(
        set(directories),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        if not directory.is_absolute() or not directory.anchor:
            continue
        anchor_fd = _open_absolute_directory_fd(Path(directory.anchor))
        try:
            _remove_created_directory(
                anchor_fd,
                Path(*directory.parts[1:]),
            )
        except (OSError, ProjectPathError, ConcurrentModificationError):
            pass
        finally:
            os.close(anchor_fd)


def _atomic_write_batch_dirfd(requests: list[PreparedWrite], *, root: Path) -> None:
    canonical = canonical_root(root)
    root_fd, created_root_directories = _open_or_create_absolute_directory_fd(canonical)
    seen: set[str] = set()
    staged: list[_StagedWrite] = []
    created_directories: list[Path] = []
    succeeded = False
    try:
        for request in requests:
            path, relative = _project_path_and_relative(root, request.path)
            key = os.path.normcase(str(relative))
            if key in seen:
                raise ValueError(f"Duplicate write target in one transaction: {relative}")
            seen.add(key)

            parent_fd, created = _open_relative_directory(
                root_fd,
                relative.parent,
                create=True,
            )
            created_directories.extend(
                item for item in created if item not in created_directories
            )
            try:
                snapshot = _read_regular_at(parent_fd, _final_name(relative))
                original = snapshot[0] if snapshot is not None else None
                original_mode = snapshot[1] if snapshot is not None else 0o644
                actual_signature = content_signature(original) if original is not None else None
                if actual_signature != request.expected_signature:
                    raise ConcurrentModificationError(
                        f"Concurrent modification detected for {relative}: expected "
                        f"{request.expected_signature or 'missing'}, got "
                        f"{actual_signature or 'missing'}"
                    )
                data = request.content.encode("utf-8")
                temporary_name, temporary_identity = _stage_bytes(
                    path,
                    data,
                    original_mode,
                    parent_fd=parent_fd,
                )
                staged.append(
                    _StagedWrite(
                        request=PreparedWrite(
                            path,
                            request.content,
                            request.expected_signature,
                        ),
                        relative=relative,
                        original=original,
                        original_mode=original_mode,
                        new_signature=content_signature(data),
                        parent_fd=parent_fd,
                        root_fd=root_fd,
                        temporary_name=temporary_name,
                        temporary_identity=temporary_identity,
                    )
                )
                parent_fd = -1
            finally:
                if parent_fd >= 0:
                    os.close(parent_fd)

        for stage in staged:
            _assert_parent_reachable(root_fd, stage.relative.parent, stage.parent_fd)
            if (
                _signature_at(stage.parent_fd, _final_name(stage.relative))
                != stage.request.expected_signature
            ):
                raise ConcurrentModificationError(
                    f"Concurrent modification detected after staging {stage.relative}"
                )

        for stage in staged:
            _commit_staged(stage)
        succeeded = True
    except BaseException as exc:
        rollback_errors: list[str] = []
        for stage in reversed(staged):
            if not stage.committed:
                continue
            try:
                _rollback_committed(stage)
            except (OSError, ProjectPathError, ConcurrentModificationError) as rollback_exc:
                rollback_errors.append(f"{stage.relative}: {rollback_exc}")
        if rollback_errors:
            raise ConcurrentModificationError(
                f"Write transaction failed ({exc}); rollback also failed: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    finally:
        cleanup_errors: list[str] = []
        for stage in staged:
            try:
                if stage.temporary_name is not None:
                    _unlink_at(
                        stage.parent_fd,
                        stage.temporary_name,
                        expected_identity=stage.temporary_identity,
                    )
            except (OSError, ProjectPathError, ConcurrentModificationError) as cleanup_exc:
                cleanup_errors.append(f"{stage.relative}: {cleanup_exc}")
        if not succeeded:
            for relative in sorted(
                set(created_directories),
                key=lambda item: len(item.parts),
                reverse=True,
            ):
                try:
                    _remove_created_directory(root_fd, relative)
                except (OSError, ProjectPathError, ConcurrentModificationError):
                    pass
        for stage in staged:
            os.close(stage.parent_fd)
        os.close(root_fd)
        if not succeeded:
            _remove_created_absolute_directories(created_root_directories)
        if cleanup_errors:
            raise ConcurrentModificationError(
                "Could not safely clean staged files: " + "; ".join(cleanup_errors)
            )


def atomic_write_batch(
    writes: Iterable[PreparedWrite],
    *,
    root: Path,
) -> None:
    """Preflight and stage every write before committing; roll back on failure."""
    requests = list(writes)
    if not requests:
        return
    require_mutation_capability("write")
    _atomic_write_batch_dirfd(requests, root=root)


def atomic_write_text(
    path: Path,
    content: str,
    *,
    root: Path,
    expected_signature: str | None,
) -> None:
    """Atomically replace one project file after checking its observed version."""
    atomic_write_batch(
        [PreparedWrite(path, content, expected_signature)],
        root=root,
    )


def _archive_project_file_dirfd(
    source: Path,
    destination: Path,
    destination_content: str,
    *,
    root: Path,
    expected_source_signature: str,
) -> None:
    """Archive through held parent descriptors and restore the source on failure."""
    canonical = canonical_root(root)
    source, source_relative = _project_path_and_relative(root, source)
    destination, destination_relative = _project_path_and_relative(root, destination)
    if source_relative == destination_relative:
        raise ValueError("Archive source and destination must differ")

    root_fd = _open_absolute_directory_fd(canonical)
    source_parent_fd: int | None = None
    destination_parent_fd: int | None = None
    created_directories: list[Path] = []
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    destination_identity: tuple[int, int] | None = None
    source_unlink_attempted = False
    original: bytes | None = None
    original_mode = 0o644
    new_signature = content_signature(destination_content.encode("utf-8"))

    try:
        source_parent_fd, _created = _open_relative_directory(
            root_fd,
            source_relative.parent,
            create=False,
        )
        destination_parent_fd, created_directories = _open_relative_directory(
            root_fd,
            destination_relative.parent,
            create=True,
        )
        _assert_parent_reachable(
            root_fd,
            source_relative.parent,
            source_parent_fd,
        )
        _assert_parent_reachable(
            root_fd,
            destination_relative.parent,
            destination_parent_fd,
        )

        source_name = _final_name(source_relative)
        destination_name = _final_name(destination_relative)
        source_snapshot = _read_regular_snapshot_at(source_parent_fd, source_name)
        if source_snapshot is None:
            raise ConcurrentModificationError(
                f"Archive source disappeared: {source_relative}"
            )
        original, original_mode, source_identity = source_snapshot
        actual_signature = content_signature(original)
        if actual_signature != expected_source_signature:
            raise ConcurrentModificationError(
                f"Concurrent modification detected for archive source {source_relative}"
            )
        if _entry_identity_at(source_parent_fd, source_name) != source_identity:
            raise ConcurrentModificationError(
                f"Archive source changed while opening {source_relative}"
            )
        if _read_regular_snapshot_at(destination_parent_fd, destination_name) is not None:
            raise ConcurrentModificationError(
                f"Archive destination already exists: {destination_relative}"
            )

        data = destination_content.encode("utf-8")
        temporary_name, temporary_identity = _stage_bytes(
            destination,
            data,
            original_mode,
            parent_fd=destination_parent_fd,
        )
        try:
            _link_at(
                destination_parent_fd,
                temporary_name,
                destination_parent_fd,
                destination_name,
            )
        except FileExistsError as exc:
            raise ConcurrentModificationError(
                f"Archive destination appeared concurrently: {destination_relative}"
            ) from exc
        destination_identity = temporary_identity
        if not _unlink_at(
            destination_parent_fd,
            temporary_name,
            expected_identity=temporary_identity,
        ):
            raise ConcurrentModificationError(
                f"Archive staging file disappeared for {destination_relative}"
            )
        temporary_name = None
        _fsync_directory(directory_fd=destination_parent_fd)

        if not _anchored_file_matches(
            destination_parent_fd,
            destination_name,
            expected_identity=destination_identity,
            expected_signature=new_signature,
        ):
            raise ConcurrentModificationError(
                f"Archived plan verification failed: {destination_relative}"
            )
        if not _anchored_file_matches(
            source_parent_fd,
            source_name,
            expected_identity=source_identity,
            expected_signature=expected_source_signature,
        ):
            raise ConcurrentModificationError(
                f"Archive source changed before removal: {source_relative}"
            )
        _assert_parent_reachable(
            root_fd,
            source_relative.parent,
            source_parent_fd,
        )
        _assert_parent_reachable(
            root_fd,
            destination_relative.parent,
            destination_parent_fd,
        )

        source_unlink_attempted = True
        if not _unlink_at(
            source_parent_fd,
            source_name,
            expected_identity=source_identity,
        ):
            raise ConcurrentModificationError(
                f"Archive source disappeared before removal: {source_relative}"
            )
        _fsync_directory(directory_fd=source_parent_fd)
        if not _anchored_file_matches(
            destination_parent_fd,
            destination_name,
            expected_identity=destination_identity,
            expected_signature=new_signature,
        ):
            raise ConcurrentModificationError(
                f"Archived plan verification failed: {destination_relative}"
            )
        _assert_parent_reachable(
            root_fd,
            destination_relative.parent,
            destination_parent_fd,
        )
    except BaseException as exc:
        rollback_errors: list[str] = []
        if (
            source_unlink_attempted
            and original is not None
            and source_parent_fd is not None
        ):
            try:
                _restore_regular_at(
                    source_parent_fd,
                    _final_name(source_relative),
                    display_path=source,
                    data=original,
                    mode=original_mode,
                    expected_signature=expected_source_signature,
                )
            except (OSError, ProjectPathError, ConcurrentModificationError) as restore_exc:
                rollback_errors.append(
                    f"source restoration failed for {source_relative}: {restore_exc}"
                )

        if destination_identity is not None and destination_parent_fd is not None:
            try:
                if _anchored_file_matches(
                    destination_parent_fd,
                    _final_name(destination_relative),
                    expected_identity=destination_identity,
                    expected_signature=new_signature,
                ):
                    _unlink_at(
                        destination_parent_fd,
                        _final_name(destination_relative),
                        expected_identity=destination_identity,
                    )
                    _fsync_directory(directory_fd=destination_parent_fd)
            except (OSError, ProjectPathError, ConcurrentModificationError) as cleanup_exc:
                rollback_errors.append(
                    f"destination rollback failed for {destination_relative}: {cleanup_exc}"
                )

        if (
            temporary_name is not None
            and temporary_identity is not None
            and destination_parent_fd is not None
        ):
            try:
                _unlink_at(
                    destination_parent_fd,
                    temporary_name,
                    expected_identity=temporary_identity,
                )
                temporary_name = None
            except (OSError, ProjectPathError, ConcurrentModificationError) as cleanup_exc:
                rollback_errors.append(
                    f"staging cleanup failed for {destination_relative}: {cleanup_exc}"
                )

        for relative in sorted(
            set(created_directories),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                _remove_created_directory(root_fd, relative)
            except (OSError, ProjectPathError, ConcurrentModificationError):
                pass

        if rollback_errors:
            raise ConcurrentModificationError(
                f"Archive transaction failed ({exc}); " + "; ".join(rollback_errors)
            ) from exc
        raise
    finally:
        if source_parent_fd is not None:
            os.close(source_parent_fd)
        if destination_parent_fd is not None:
            os.close(destination_parent_fd)
        os.close(root_fd)


def archive_project_file_safe(
    source: Path,
    destination: Path,
    destination_content: str,
    *,
    root: Path,
    expected_source_signature: str,
) -> None:
    """Archive one source without losing its original bytes on transaction failure."""
    require_mutation_capability("archive")
    _archive_project_file_dirfd(
        source,
        destination,
        destination_content,
        root=root,
        expected_source_signature=expected_source_signature,
    )


def unlink_project_file_safe(
    path: Path,
    *,
    root: Path,
    expected_signature: str,
    missing_ok: bool = False,
) -> bool:
    """Unlink a version-checked project file without rewalking an attacker path."""
    path, relative = _project_path_and_relative(root, path)
    canonical = canonical_root(root)
    require_mutation_capability("delete")
    root_fd = _open_absolute_directory_fd(canonical)
    parent_fd: int | None = None
    try:
        parent_fd, _created = _open_relative_directory(
            root_fd,
            relative.parent,
            create=False,
        )
        _assert_parent_reachable(root_fd, relative.parent, parent_fd)
        name = _final_name(relative)
        actual_signature = _signature_at(parent_fd, name)
        if actual_signature is None and missing_ok:
            return False
        if actual_signature != expected_signature:
            raise ConcurrentModificationError(
                f"Concurrent modification detected before removing {relative}"
            )
        identity = _entry_identity_at(parent_fd, name)
        _assert_parent_reachable(root_fd, relative.parent, parent_fd)
        if not _unlink_at(parent_fd, name, expected_identity=identity):
            if missing_ok:
                return False
            raise ConcurrentModificationError(f"File disappeared before removing {relative}")
        _fsync_directory(directory_fd=parent_fd)
        _assert_parent_reachable(root_fd, relative.parent, parent_fd)
        return True
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
        os.close(root_fd)


@contextmanager
def project_lock(
    root: Path,
    *,
    timeout: float = 10.0,
    required_capability: str = "write",
) -> Iterator[None]:
    """Serialize stewardship writers with a portable advisory file lock."""
    require_mutation_capability(required_capability)
    canonical = canonical_root(root)
    lock_identity = os.path.normcase(str(canonical))
    digest = hashlib.sha256(lock_identity.encode("utf-8")).hexdigest()[:24]
    lock_path = Path(tempfile.gettempdir()) / f"charlie-project-steward-{digest}.lock"
    if lock_path.is_symlink():
        raise ProjectPathError(f"Refusing symlink lock file: {lock_path}")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock_path, flags, 0o600)
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
            os.fsync(fd)
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise ConcurrentModificationError(
                        f"Timed out waiting for stewardship lock for {canonical}"
                    )
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
