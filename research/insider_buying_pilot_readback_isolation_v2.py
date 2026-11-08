"""Exact read-only isolation for the additive saved-dossier successor.

No helper installs a profile or launches a process. The caller must start its
source/Git and saved-leaf workers under the returned native profiles before
executing trusted code. Old source constructors and old receipts stay frozen.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
BRANCH = "codex/strategy-insider-buying"
USER = Path("/Users/sheltonchen")
FAMILY = ROOT.parent
EXPECTED_COMMON = FAMILY / "trading_agent/.git"
EXPECTED_GITDIR = EXPECTED_COMMON / "worktrees" / ROOT.name
SUPPORTED_PYTHON = USER / ".venvs/trading_agent-py313/bin/python3.13"
SUPPORTED_BASE = Path("/opt/homebrew/Cellar/python@3.13/3.13.15/Frameworks/Python.framework/Versions/3.13")
GIT_IMAGE = Path("/Library/Developer/CommandLineTools/usr/bin/git")
GIT_LIBRARIES = Path("/Library/Developer/CommandLineTools/usr/lib")
EPOCH_ROOT = USER / "Library/Application Support/trading_agent/insider_buying/custody/ib-storage-transition-dossier-v1-20261107-once"
OUTPUT_NAMES = ("reservation.json", "observation-started.json", "transition.json", "dossier.json", "complete.json")
MAX_ADMIN = 128 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")


class IsolationError(ValueError):
    """Fixed refusal only: never emit private config contents or paths."""


def need(ok, code="isolation_refused"):
    if not ok:
        raise IsolationError(code)


def raw(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise IsolationError("shape_refused") from None


def _absolute(path):
    need(type(path) in {str, Path} or isinstance(path, Path), "path_refused")
    original = str(path)
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts and "." not in path.parts
         and str(path) == original == os.path.normpath(original), "path_refused")
    return path


def protected_roots():
    return (FAMILY, USER / "Documents", USER / "Desktop", USER / "Downloads",
            USER / "Library", Path("/Library/Keychains"), Path("/Volumes"))


def _ancestors(path):
    result = {}
    for item in (path, *path.parents):
        try:
            info = item.stat()
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            raise IsolationError("metadata_refused") from None
        need(stat.S_ISDIR(info.st_mode), "metadata_refused")
        result[item] = (info.st_dev, info.st_ino)
    return result


def require_disjoint(directories, protected=None):
    """Reject lexical coverage/nesting and physical endpoint-ancestor aliases."""
    directories = tuple(_absolute(p) for p in directories)
    protected = tuple(_absolute(p) for p in (protected_roots() if protected is None else protected))
    need(bool(directories) and bool(protected), "runtime_refused")
    try:
        resolved = {path: path.resolve() for path in (*directories, *protected)}
    except (OSError, RuntimeError, ValueError):
        raise IsolationError("metadata_refused") from None
    metadata = {path: _ancestors(path) for path in {*directories, *protected, *resolved.values()}}
    for directory in directories:
        for target in protected:
            for candidate in (directory, resolved[directory]):
                for forbidden in (target, resolved[target]):
                    need(not candidate.is_relative_to(forbidden) and not forbidden.is_relative_to(candidate),
                         "runtime_refused")
                    did, tid = metadata[candidate].get(candidate), metadata[forbidden].get(forbidden)
                    need(not (did is not None and did in metadata[forbidden].values())
                         and not (tid is not None and tid in metadata[candidate].values()),
                         "runtime_refused")


def validate_source_names(sources):
    names = tuple(sources)
    need(0 < len(names) <= 2048 and len(set(names)) == len(names), "source_refused")
    for name in names:
        need(type(name) is str and re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.py", name)
             and Path(name).as_posix() == name and not Path(name).is_absolute()
             and not any(p in {".", "..", "artifacts"} for p in Path(name).parts), "source_refused")
        try:
            need((ROOT / name).resolve() == ROOT / name, "source_refused")
        except (OSError, RuntimeError, ValueError):
            raise IsolationError("source_refused") from None
    return names


def _directory_version(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            getattr(info, "st_flags", 0))


def _leaf_version(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, "st_flags", 0))


def _read_admin(path, *, optional=False):
    """No-follow each directory and leaf; return only bounded body plus seal."""
    path = _absolute(path)
    descriptors, versions, leaf = [], [], None
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd); versions.append(_directory_version(os.fstat(fd)))
        for component in path.parent.parts[1:]:
            parent = fd
            try:
                fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                need(optional, "admin_refused")
                return None, {"present": False}
            descriptors.append(fd); versions.append(_directory_version(os.fstat(fd)))
            need(versions[-1] == _directory_version(os.stat(component, dir_fd=parent,
                 follow_symlinks=False)), "admin_refused")
        try:
            leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            need(optional, "admin_refused")
            return None, {"present": False}
        before = os.fstat(leaf)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and before.st_uid == os.geteuid() and not stat.S_IMODE(before.st_mode) & 0o022
             and 0 <= before.st_size <= MAX_ADMIN, "admin_refused")
        body = os.pread(leaf, MAX_ADMIN + 1, 0)
        need(len(body) == before.st_size and _leaf_version(before) == _leaf_version(os.fstat(leaf))
             == _leaf_version(os.stat(path.name, dir_fd=fd, follow_symlinks=False)), "admin_refused")
        return body, {"present": True, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                      "version": list(_leaf_version(before))}
    except IsolationError:
        raise
    except (OSError, ValueError):
        raise IsolationError("admin_refused") from None
    finally:
        primary = sys.exc_info()[0] is not None
        failed = False
        if leaf is not None:
            try: os.close(leaf)
            except OSError: failed = True
        for index, (descriptor, version) in enumerate(zip(descriptors, versions)):
            try:
                need(_directory_version(os.fstat(descriptor)) == version, "admin_refused")
                if index:
                    need(_directory_version(os.stat(path.parent.parts[index],
                         dir_fd=descriptors[index - 1], follow_symlinks=False)) == version,
                         "admin_refused")
            except Exception: failed = True
        for descriptor in reversed(descriptors):
            try: os.close(descriptor)
            except OSError: failed = True
        need(primary or not failed, "admin_refused")


def _admin_paths():
    return (ROOT / ".git", EXPECTED_GITDIR / "commondir", EXPECTED_GITDIR / "gitdir",
            EXPECTED_COMMON / "config", EXPECTED_GITDIR / "config.worktree",
            EXPECTED_COMMON / "info/exclude")


def _admin_locations():
    """The fixed shared metadata exception never covers current/private DATA."""
    try:
        require_disjoint((EXPECTED_COMMON, EXPECTED_GITDIR),
            (ROOT, USER / "Library", Path("/Library/Keychains"), Path("/Volumes"),
             USER / "Desktop", USER / "Downloads"))
        need(EXPECTED_GITDIR.resolve() == EXPECTED_GITDIR and EXPECTED_COMMON.resolve() == EXPECTED_COMMON
             and EXPECTED_GITDIR == EXPECTED_COMMON / "worktrees" / ROOT.name, "admin_refused")
    except (IsolationError, OSError, RuntimeError, ValueError):
        raise IsolationError("admin_refused") from None


def _optional_admin(path):
    return path in {EXPECTED_GITDIR / "config.worktree", EXPECTED_COMMON / "info/exclude"}


def discover_admin():
    """Fixed lane pointers only; never ask an unsandboxed Git for common-dir."""
    _admin_locations()
    pointer, pin = _read_admin(ROOT / ".git")
    need(pointer == ("gitdir: " + str(EXPECTED_GITDIR) + "\n").encode(), "admin_refused")
    common, common_pin = _read_admin(EXPECTED_GITDIR / "commondir")
    need(common == b"../..\n", "admin_refused")
    backlink, backlink_pin = _read_admin(EXPECTED_GITDIR / "gitdir")
    need(backlink == (str(ROOT / ".git") + "\n").encode(), "admin_refused")
    files = {str(ROOT / ".git"): pin, str(EXPECTED_GITDIR / "commondir"): common_pin,
             str(EXPECTED_GITDIR / "gitdir"): backlink_pin}
    for path in _admin_paths()[3:]:
        _body, files[str(path)] = _read_admin(path, optional=_optional_admin(path))
    return {"common": str(EXPECTED_COMMON), "worktree": str(EXPECTED_GITDIR), "files": files}


def _layout(layout):
    need(type(layout) is dict and set(layout) == {"common", "worktree", "files"}
         and layout["common"] == str(EXPECTED_COMMON) and layout["worktree"] == str(EXPECTED_GITDIR)
         and type(layout["files"]) is dict and set(layout["files"]) == {str(p) for p in _admin_paths()},
         "admin_refused")
    for path, pin in layout["files"].items():
        need(type(pin) is dict and type(pin.get("present")) is bool, "admin_refused")
        if pin["present"]:
            need(set(pin) == {"present", "bytes", "sha256", "version"}
                 and type(pin["bytes"]) is int and 0 <= pin["bytes"] <= MAX_ADMIN
                 and type(pin["sha256"]) is str and _SHA.fullmatch(pin["sha256"])
                 and type(pin["version"]) is list and len(pin["version"]) == 10
                 and all(type(v) is int and v >= 0 for v in pin["version"])
                 and pin["bytes"] == pin["version"][6], "admin_refused")
        else:
            need(_optional_admin(Path(path)) and set(pin) == {"present"}, "admin_refused")
    return layout


def check_admin(layout):
    _layout(layout)
    need(raw(discover_admin()) == raw(layout), "admin_changed")


def git_environment(layout):
    _layout(layout)
    return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_COUNT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
            "GIT_ATTR_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}


def _safe_pathspec(value):
    return bool(type(value) is str and (value == ".gitignore" or
                re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*(?:[A-Za-z0-9_.-]+\.py|\.gitignore)", value))
                and Path(value).as_posix() == value and ".." not in Path(value).parts)


def git_command(arguments, layout):
    _layout(layout)
    need(type(arguments) in {tuple, list} and arguments and all(type(x) is str for x in arguments), "git_refused")
    command, *args = arguments
    options = {
        "rev-parse": {"--show-toplevel", "--git-common-dir", "--absolute-git-dir", "--verify", "--abbrev-ref", "--symbolic-full-name", "--show-object-format", "HEAD", "HEAD^{commit}", "refs/heads/" + BRANCH},
        "status": {"--porcelain=v1", "--porcelain=v2", "--branch", "--untracked-files=all", "--ignored=no", "-z"},
        "ls-tree": {"-r", "-d", "-z", "--name-only", "--full-tree"},
        "ls-files": {"--stage", "-z", "--cached", "--error-unmatch", "--full-name", "--"},
        "diff": {"--no-ext-diff", "--no-textconv", "--name-only", "--name-status", "--exit-code", "--quiet", "--cached", "--"},
    }
    if command == "show":
        need(len(args) == 1 and ":" in args[0], "git_refused")
        head, path = args[0].split(":", 1)
        need(_HEAD.fullmatch(head) and _safe_pathspec(path), "git_refused")
    else:
        need(command in options and all(x in options[command] or _HEAD.fullmatch(x)
             or command in {"ls-files", "diff"} and _safe_pathspec(x) for x in args), "git_refused")
    tail = (command, "--no-ext-diff", "--no-textconv", *args) if command == "diff" else tuple(arguments)
    return (str(GIT_IMAGE), "--no-pager", "--no-replace-objects", "--no-optional-locks",
            "--git-dir=" + str(EXPECTED_GITDIR), "--work-tree=" + str(ROOT),
            "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-c", "core.excludesFile=/dev/null", "-c", "core.untrackedCache=false",
            "-c", "core.preloadIndex=false", "-c", "maintenance.auto=false",
            "-c", "gc.auto=0", "-c", "credential.helper=", *tail)


def runtime_layout(python=None):
    executable = _absolute(python or sys.executable)
    base = _absolute(sys.base_prefix)
    require_disjoint((executable.parent.parent, base))
    need(executable == SUPPORTED_PYTHON and base == SUPPORTED_BASE, "runtime_refused")
    try:
        target = executable.resolve()
        need(target.is_relative_to(base.resolve()), "runtime_refused")
        directories = (Path("/System/Library"), Path("/usr/lib"), Path("/usr/share"),
                       Path("/private/var/db/dyld"), base.resolve(), executable.parent.parent.resolve(),
                       Path("/usr/share/zoneinfo").resolve())
        require_disjoint(directories)
        need(target.is_file(), "runtime_refused")
    except (OSError, RuntimeError, ValueError):
        raise IsolationError("runtime_refused") from None
    images = [executable, target]
    relaunch = target.parents[1] / "Resources/Python.app/Contents/MacOS/Python"
    if relaunch.is_file():
        images.append(relaunch.resolve())
    libraries = []
    for relative in ("openssl@3/lib/libssl.3.dylib", "openssl@3/lib/libcrypto.3.dylib",
                     "xz/lib/liblzma.5.dylib", "sqlite/lib/libsqlite3.0.dylib",
                     "gettext/lib/libintl.8.dylib", "readline/lib/libreadline.8.dylib",
                     "zstd/lib/libzstd.1.dylib", "mpdecimal/lib/libmpdec.4.dylib"):
        path = Path("/opt/homebrew/opt") / relative
        if path.is_file():
            libraries.extend((path, path.resolve()))
    require_disjoint(tuple(image.resolve().parent for image in (*images, *libraries)))
    return tuple(dict.fromkeys(directories)), tuple(dict.fromkeys(images)), tuple(dict.fromkeys(libraries))


def _source_directories(paths):
    result = []
    for value in paths:
        path = _absolute(value)
        need(path.is_relative_to(ROOT) and path.resolve() == path and path.is_dir(), "source_refused")
        result.append(path)
    need(len(result) == len(set(result)), "source_refused")
    return tuple(result)


def _ignore_leaves(paths):
    result = []
    for value in paths:
        path = _absolute(value)
        need(path.is_relative_to(ROOT) and path.name == ".gitignore" and path.resolve() == path
             and path.is_file(), "source_refused")
        result.append(path)
    need(len(result) == len(set(result)), "source_refused")
    return tuple(result)


def policy(*, sources, data_leaves=(), admin=None, git=False, controller=False, source_directories=(),
           gitignore_leaves=(), runtime_directories=None, python=None):
    """Build from exact sets; never narrow a broad policy by string replacement."""
    names = validate_source_names(sources)
    need(type(git) is bool and type(controller) is bool, "profile_refused")
    data = tuple(_absolute(p) for p in data_leaves)
    expected = {EPOCH_ROOT / name for name in OUTPUT_NAMES}
    need(not data or len(data) == 5 and len(set(data)) == 5 and set(data) == expected, "data_scope_refused")
    need(not git or not data, "data_scope_refused")
    need(not controller or not git and not data, "profile_refused")
    need(git or admin is None and not source_directories and not gitignore_leaves, "profile_refused")
    directories, images, libraries = runtime_layout(python)
    if runtime_directories is not None:
        supplied = tuple(_absolute(p) for p in runtime_directories)
        require_disjoint(supplied)
        need(set(supplied) == set(directories), "runtime_refused")
    dirs = _source_directories(source_directories)
    ignores = _ignore_leaves(gitignore_leaves)
    if git:
        _layout(admin)
        _admin_locations()
        require_disjoint((*directories, GIT_LIBRARIES), (*protected_roots(), EXPECTED_COMMON))
        directories = (*directories, GIT_LIBRARIES)
    need(GIT_IMAGE.resolve() == GIT_IMAGE and GIT_IMAGE.is_file(), "runtime_refused")
    leaves = (*[ROOT / name for name in names], *data, *images, *libraries, GIT_IMAGE,
              Path("/dev/null"), Path("/dev/urandom"), Path("/dev/random"),
              Path("/etc/localtime"), Path("/private/etc/localtime"), *ignores)
    if git:
        leaves = (*leaves, ROOT / ".git", GIT_IMAGE)
    ancestors = {Path("/")}
    for path in (*leaves, *directories, *dirs):
        ancestors.update(path.parents)
    if git:
        for path in (EXPECTED_COMMON, EXPECTED_GITDIR, *_admin_paths()):
            ancestors.update(path.parents)
    q = lambda p: json.dumps(str(p))
    profile = "(version 1)(allow default)(deny network*)(deny process-exec)(deny file-write*)(deny file-read-data)"
    if not git:
        profile += "(deny process-fork)"
    else:
        # Git opens its discard sink O_RDWR even for rev-parse. This grants
        # no ordinary file write/create/unlink or saved-DATA capability.
        profile += '(allow file-write-data (literal "/dev/null"))'
    if not controller:
        profile += "(allow process-exec " + " ".join("(literal " + q(p) + ")" for p in (*images, *((GIT_IMAGE,) if git else ()))) + ")"
    profile += "(allow file-read-data " + " ".join("(subpath " + q(p) + ")" for p in directories)
    if git:
        profile += " (subpath " + q(EXPECTED_COMMON) + ")"
    profile += " " + " ".join("(literal " + q(p) + ")" for p in (*leaves, *dirs, *sorted(ancestors))) + ")"
    return profile
