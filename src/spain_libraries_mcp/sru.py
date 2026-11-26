"""SRU 1.2 client (HTTP search using CQL), used for the National Library of Spain (BNE)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

from . import __version__

USER_AGENT = f"spain-libraries-mcp/{__version__} (+personal use; occasional queries)"


@dataclass
class SruResult:
    hits: int
    records: list[str] = field(default_factory=list)  # MARCXML for each record


async def search(base_url: str, cql: str, *, max_records: int = 10, timeout: float = 20,
                 client: httpx.AsyncClient | None = None) -> SruResult:
    params = {
        "operation": "searchRetrieve",
        "version": "1.2",
        "query": cql,
        "recordSchema": "marcxml",
        "startRecord": "1",
        "maximumRecords": str(max_records),
    }
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT})
    try:
        r = await client.get(base_url, params=params)
        r.raise_for_status()
        return parse_response(r.text)
    finally:
        if own:
            await client.aclose()


def parse_response(text: str) -> SruResult:
    root = ET.fromstring(text)
    local = lambda el: el.tag.split("}", 1)[-1] if isinstance(el.tag, str) else ""  # noqa: E731
    hits = 0
    for el in root.iter():
        if local(el) == "numberOfRecords":
            try:
                hits = int((el.text or "0").strip() or 0)
            except ValueError:
                hits = 0
        if local(el) == "diagnostic":
            msg = " ".join((d.text or "").strip() for d in el.iter() if local(d) in ("message", "details"))
            raise RuntimeError(f"SRU diagnostic: {msg}")
    recs = []
    for el in root.iter():
        if local(el) == "recordData":
            for child in el:
                recs.append(ET.tostring(child, encoding="unicode"))
                break
    return SruResult(hits=hits, records=recs)
