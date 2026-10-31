"""Move a finished file to its name without ever replacing a file that is already there.

Each desktop system has an atomic move that fails instead of replacing: renamex_np with RENAME_EXCL on macOS,
renameat2 with RENAME_NOREPLACE on Linux, and plain rename on Windows. Some disks don't support it (exFAT on
macOS, older Linux file systems, some network shares), so rename_no_replace says so and the caller falls back.
"""
import ctypes
import errno
import os
import sys

_UNSUPPORTED = frozenset({errno.ENOTSUP, errno.EOPNOTSUPP, errno.EINVAL, errno.ENOSYS, errno.EXDEV})
_RENAME_EXCL = 0x4  # macOS <sys/stdio.h>
_RENAME_NOREPLACE = 0x1  # Linux <linux/fs.h>
_AT_FDCWD = -100


def _libc_call():
    if sys.platform == "win32":
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except OSError:
        return None
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        call = libc.renamex_np
        call.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        return lambda src, dst: call(src, dst, _RENAME_EXCL)
    if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):  # glibc 2.28 and later
        call = libc.renameat2
        call.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        return lambda src, dst: call(_AT_FDCWD, src, _AT_FDCWD, dst, _RENAME_NOREPLACE)
    return None


_CALL = _libc_call()


def rename_no_replace(src: str | os.PathLike, dst: str | os.PathLike) -> bool:
    """Move src to dst in one step. Raise FileExistsError if dst exists, and leave both untouched. Return False
    when this system or disk has no such move, so the caller must choose another way."""
    if sys.platform == "win32":
        os.rename(src, dst)  # MoveFileExW without MOVEFILE_REPLACE_EXISTING: fails if dst exists
        return True
    if _CALL is None:
        return False
    if _CALL(os.fsencode(src), os.fsencode(dst)) == 0:
        return True
    code = ctypes.get_errno()
    if code == errno.EEXIST:
        raise FileExistsError(code, os.strerror(code), os.fspath(dst))
    if code in _UNSUPPORTED:
        return False
    raise OSError(code, os.strerror(code), os.fspath(src), None, os.fspath(dst))
