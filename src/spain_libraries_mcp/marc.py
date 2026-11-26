"""Conversion of MARCXML / OPAC records into simple structures (Book + Holdings).

Each integrated library system stores holdings in different fields:
  - Koha (Galicia, many smaller networks): 952
  - Alma / Ex Libris (BNE, CSIC): AVA (computed availability)
  - Sierra / Innovative (Aladí): 907 $i (libraries), 945 (items)
  - AbsysNet (CCBIP, REBIUN, Euskadi...): varies by installation; 850/852/949/999
Additionally, if the server supports Z39.50 OPAC record syntax, it returns <holdings>
with normalized circulation data (availableNow), which is the most reliable source.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field

NS = "{http://www.loc.gov/MARC21/slim}"
HOLDINGS_FIELDS = {"850", "852", "907", "945", "949", "952", "999", "AVA"}


@dataclass
class Holding:
    library: str | None = None
    location: str | None = None
    call_number: str | None = None
    status: str | None = None  # available | checked_out | not_for_loan | unavailable | lost | unknown
    available: int | None = None
    total: int | None = None
    source: str = ""  # MARC field / opac source
    details: dict[str, str] = field(default_factory=dict)


@dataclass
class Book:
    catalog: str
    id: str | None = None
    title: str | None = None
    author: str | None = None
    edition: str | None = None
    publisher: str | None = None
    year: str | None = None
    isbn: list[str] = field(default_factory=list)
    language: str | None = None
    subjects: list[str] = field(default_factory=list)
    holdings: list[Holding] = field(default_factory=list)
    link: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["holdings"] = [{k: v for k, v in h.items() if v not in (None, {}, "")} for h in d["holdings"]]
        return {k: v for k, v in d.items() if v not in (None, [], "")}


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip(" /:;,.=")
    return s or None


def _strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _find_record(root: ET.Element) -> ET.Element | None:
    if root.tag == "record":
        return root
    for el in root.iter("record"):
        if el.find("datafield") is not None or el.find("controlfield") is not None:
            return el
    return None


def _fields(rec: ET.Element) -> list[tuple[str, dict[str, list[str]]]]:
    out = []
    for df in rec.findall("datafield"):
        subs: dict[str, list[str]] = {}
        for sf in df.findall("subfield"):
            subs.setdefault(sf.get("code", "?"), []).append((sf.text or "").strip())
        out.append((df.get("tag", ""), subs))
    return out


def _first(fields, tag: str, code: str) -> str | None:
    for t, s in fields:
        if t == tag and s.get(code):
            return s[code][0]
    return None


def parse_marcxml(xml: str, catalog: str, profile: str = "generic") -> Book | None:
    try:
        root = _strip_ns(ET.fromstring(xml))
    except ET.ParseError:
        return None
    rec = _find_record(root)
    if rec is None:
        return None
    f = _fields(rec)
    ctrl = {cf.get("tag"): (cf.text or "") for cf in rec.findall("controlfield")}
    c008 = ctrl.get("008", "")

    title = " ".join(x for x in [_first(f, "245", "a"), _first(f, "245", "b")] if x)
    author = _first(f, "100", "a") or _first(f, "110", "a") or _first(f, "700", "a")
    pub = next((s for t, s in f if t in ("264", "260") and (s.get("b") or s.get("c"))), {})
    year = None
    if pub.get("c"):
        m = re.search(r"\d{4}", pub["c"][0])
        year = m.group(0) if m else None
    if not year and len(c008) >= 11 and c008[7:11].isdigit():
        year = c008[7:11]

    book = Book(
        catalog=catalog,
        id=_clean(ctrl.get("001")),
        title=_clean(title),
        author=_clean(author),
        edition=_clean(_first(f, "250", "a")),
        publisher=_clean(pub.get("b", [None])[0]),
        year=year,
        isbn=sorted({re.sub(r"[^0-9Xx]", "", v.split(" ")[0]) for t, s in f if t == "020" for v in s.get("a", []) if v}
                    - {""}),
        language=c008[35:38].strip() or None if len(c008) >= 38 else None,
        subjects=[m for t, s in f if t.startswith("6") and s.get("a") if (m := _clean(s["a"][0]))][:8],
    )
    book.holdings = marc_holdings(f, profile)
    return book


def marc_holdings(fields, profile: str) -> list[Holding]:
    out: list[Holding] = []
    for tag, s in fields:
        if tag not in HOLDINGS_FIELDS:
            continue
        g = lambda c: (s.get(c) or [None])[0]  # noqa: E731
        det = {k: "; ".join(v) for k, v in s.items()}
        if tag == "952":  # Koha
            if g("q"):
                status = "checked_out"
            elif g("1") not in (None, "0") or g("0") not in (None, "0"):
                status = "lost"
            elif g("7") not in (None, "0"):
                status = "not_for_loan"
            else:
                status = "available"
            out.append(Holding(library=g("b") or g("a"), location=g("c"), call_number=g("o"),
                               status=status, source="952", details=det))
        elif tag == "AVA":  # Alma
            avail = (g("e") or "").lower()
            tot = _int(g("f"))
            unavail = _int(g("g")) or 0
            out.append(Holding(
                library=g("q") or g("b"), location=g("c"), call_number=g("d"),
                status={"available": "available", "unavailable": "checked_out"}.get(avail, "unknown"),
                total=tot, available=max(0, tot - unavail) if tot is not None else None,
                source="AVA", details=det))
        elif tag == "907" and s.get("i"):  # Sierra: codes of libraries holding the item
            for code in s["i"]:
                out.append(Holding(library=code, status="unknown", source="907$i"))
        elif tag == "945":  # Sierra item
            st = (g("s") or "").strip()
            out.append(Holding(library=g("l"), call_number=g("a"),
                               status="available" if st == "-" else ("unknown" if not st else "unavailable"),
                               source="945", details=det))
        elif tag == "852":
            out.append(Holding(library=g("a") or g("b"), location=g("c") or (g("b") if g("a") else None),
                               call_number=" ".join(x for x in [g("h"), g("i"), g("j")] if x) or None,
                               status="unknown", source="852", details=det))
        elif tag == "850":  # union catalogs: holding institutions
            for code in s.get("a", []):
                out.append(Holding(library=code, status="unknown", source="850"))
        else:  # 949 / 999 and similar: returned raw to avoid losing information
            out.append(Holding(library=g("a") or g("b") or g("m"), call_number=g("c") or g("d"),
                               status="unknown", source=tag, details=det))
    return out


def opac_holdings(opac_xml: str) -> list[Holding]:
    """Extract <holdings> from a Z39.50 OPAC syntax record."""
    try:
        root = _strip_ns(ET.fromstring(opac_xml))
    except ET.ParseError:
        return []
    out = []
    for h in root.iter("holding"):
        t = lambda n: _clean(h.findtext(n))  # noqa: E731
        circs = list(h.iter("circulation"))
        avail = sum(
            1 for c in circs
            if (an := c.find("availableNow")) is not None
            and (an.get("value") or (an.text or "").strip()) == "1"
        )
        status = "unknown"
        if circs:
            status = "available" if avail else "checked_out"
        out.append(Holding(
            library=t("nucCode") or t("localLocation"), location=t("localLocation"),
            call_number=t("callNumber"), status=status,
            available=avail if circs else None, total=len(circs) or None, source="opac",
            details={k: v for k, v in {"shelving": t("shelvingData"), "copy": t("copyNumber"),
                                       "notes": t("publicNote")}.items() if v},
        ))
    return out


def _int(s: str | None) -> int | None:
    try:
        return int(s) if s is not None else None
    except ValueError:
        return None
