"""Minimal Z39.50 client wrapping the YAZ (Index Data) ZOOM API via ctypes.

YAZ is the de facto standard for Z39.50, used by Koha, VuFind, MarcEdit, and others.
This module wraps only the ~13 ZOOM functions we need.

Installing the native library:
  - Debian/Ubuntu: apt install libyaz5   (or the `yaz` package)
  - macOS:         brew install yaz
  - Docker:        already included in the project image
You can override the library path with the `YAZ_LIB` environment variable.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import threading
from dataclasses import dataclass, field

_lib: ctypes.CDLL | None = None
_lib_lock = threading.Lock()

_CANDIDATES = [
    "libyaz.so.5",
    "libyaz.so",
    "/opt/homebrew/lib/libyaz.dylib",
    "/usr/local/lib/libyaz.dylib",
    "libyaz5.dll",
    "yaz5.dll",
]


class YazNotAvailable(RuntimeError):
    """The native libyaz library is not installed."""


class Z3950Error(RuntimeError):
    """Error returned by the Z39.50 server or connection."""

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(message)
        self.code = code


def _load() -> ctypes.CDLL:
    global _lib
    if _lib is not None:
        return _lib
    with _lib_lock:
        if _lib is not None:
            return _lib
        paths = [os.environ["YAZ_LIB"]] if os.environ.get("YAZ_LIB") else []
        found = ctypes.util.find_library("yaz")
        if found:
            paths.append(found)
        paths += _CANDIDATES
        last: Exception | None = None
        for p in paths:
            try:
                lib = ctypes.CDLL(p)
                break
            except OSError as e:
                last = e
        else:
            raise YazNotAvailable(
                "libyaz not found. Install it (apt install libyaz5 / brew install yaz) "
                f"or set YAZ_LIB. Last error: {last}"
            )

        vp, cp, ci = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
        sig = {
            "ZOOM_options_create": ([], vp),
            "ZOOM_options_set": ([vp, cp, cp], None),
            "ZOOM_options_destroy": ([vp], None),
            "ZOOM_connection_create": ([vp], vp),
            "ZOOM_connection_connect": ([vp, cp, ci], None),
            "ZOOM_connection_error": ([vp, ctypes.POINTER(cp), ctypes.POINTER(cp)], ci),
            "ZOOM_connection_search_pqf": ([vp, cp], vp),
            "ZOOM_connection_destroy": ([vp], None),
            "ZOOM_resultset_size": ([vp], ctypes.c_size_t),
            "ZOOM_resultset_record": ([vp, ctypes.c_size_t], vp),
            "ZOOM_resultset_option_set": ([vp, cp, cp], None),
            "ZOOM_resultset_destroy": ([vp], None),
            "ZOOM_record_get": ([vp, cp, ctypes.POINTER(ci)], ctypes.c_void_p),
        }
        for name, (args, res) in sig.items():
            fn = getattr(lib, name)
            fn.argtypes = args
            fn.restype = res
        _lib = lib
        return lib


def yaz_available() -> bool:
    try:
        _load()
        return True
    except YazNotAvailable:
        return False


@dataclass
class ZRecord:
    raw: bytes | None = None  # raw ISO 2709 record
    xml: str | None = None  # MARCXML converted to UTF-8 by YAZ
    opac: str | None = None  # OPAC record (with holdings) if provided by the server


@dataclass
class ZResult:
    hits: int
    records: list[ZRecord] = field(default_factory=list)


def _enc(s: str | None) -> bytes | None:
    return None if s is None else s.encode("utf-8")


def search(
    host: str,
    port: int,
    database: str,
    pqf: str,
    *,
    max_records: int = 10,
    syntax: str = "usmarc",
    charset: str = "utf-8",
    user: str | None = None,
    password: str | None = None,
    timeout: int = 20,
) -> ZResult:
    """Run a PQF query and return up to `max_records` records.

    This call is blocking: invoke it from a worker thread (`asyncio.to_thread`).
    """
    lib = _load()
    opts = lib.ZOOM_options_create()
    try:
        for k, v in {
            "databaseName": database,
            "preferredRecordSyntax": syntax,
            "timeout": str(timeout),
            "count": str(max_records),  # piggyback the first N records with the search
            "presentChunk": str(max_records),
            "user": user,
            "password": password,
        }.items():
            if v:
                lib.ZOOM_options_set(opts, _enc(k), _enc(v))
        conn = lib.ZOOM_connection_create(opts)
    finally:
        lib.ZOOM_options_destroy(opts)

    rs = None
    try:
        lib.ZOOM_connection_connect(conn, _enc(host), port)
        _check(lib, conn, f"{host}:{port}")
        rs = lib.ZOOM_connection_search_pqf(conn, _enc(pqf))
        _check(lib, conn, f"{host}:{port}")
        hits = int(lib.ZOOM_resultset_size(rs))
        out = ZResult(hits=hits)
        # Character set conversion when requesting XML: "<source>,utf-8"
        xml_type = f"xml; charset={charset},utf-8".encode() if charset.lower() not in ("utf-8", "utf8") else b"xml"
        for i in range(min(hits, max_records)):
            rec = lib.ZOOM_resultset_record(rs, i)
            if not rec:
                _check(lib, conn, f"{host}:{port}")
                break
            out.records.append(
                ZRecord(
                    raw=_get(lib, rec, b"raw"),
                    xml=_text(_get(lib, rec, xml_type)),
                    opac=_text(_get(lib, rec, b"opac")) if syntax == "opac" else None,
                )
            )
        return out
    finally:
        if rs:
            lib.ZOOM_resultset_destroy(rs)
        lib.ZOOM_connection_destroy(conn)


def _get(lib: ctypes.CDLL, rec: int, kind: bytes) -> bytes | None:
    n = ctypes.c_int(0)
    p = lib.ZOOM_record_get(rec, kind, ctypes.byref(n))
    if not p or n.value <= 0:
        return None
    return ctypes.string_at(p, n.value)


def _text(b: bytes | None) -> str | None:
    return None if b is None else b.decode("utf-8", errors="replace")


def _check(lib: ctypes.CDLL, conn: int, where: str) -> None:
    msg, add = ctypes.c_char_p(), ctypes.c_char_p()
    code = lib.ZOOM_connection_error(conn, ctypes.byref(msg), ctypes.byref(add))
    if code:
        m = (msg.value or b"").decode("utf-8", "replace")
        a = (add.value or b"").decode("utf-8", "replace")
        raise Z3950Error(f"{where}: {m} ({code}) {a}".strip(), code=code)
