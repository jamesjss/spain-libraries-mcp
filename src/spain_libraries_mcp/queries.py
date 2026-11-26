"""Query builders: PQF (Z39.50, Bib-1 attributes) and CQL (SRU)."""

from __future__ import annotations

from dataclasses import dataclass

# Standard Bib-1 Use attributes
BIB1 = {
    "title": 4,
    "author": 1003,
    "isbn": 7,
    "subject": 21,
    "text": 1016,  # "any"
}


@dataclass
class SearchCriteria:
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    subject: str | None = None
    text: str | None = None

    def items(self) -> list[tuple[str, str]]:
        out = []
        for k in ("isbn", "title", "author", "subject", "text"):
            v = getattr(self, k)
            if v and v.strip():
                v = v.strip()
                if k == "isbn":
                    v = "".join(ch for ch in v if ch.isdigit() or ch in "Xx")
                if v:
                    out.append((k, v))
        return out

    def is_empty(self) -> bool:
        return not self.items()

    def summary(self) -> str:
        return " ".join(v for _, v in self.items())


def _pqf_term(v: str) -> str:
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_pqf(c: SearchCriteria, variant: int = 0, extra: str = "") -> str:
    """Example: @and @attr 1=4 "el quijote" @attr 1=1003 "cervantes"

    For titles/authors, uses word-list structure (4=6) without right truncation,
    which is best supported by AbsysNet, Koha, and Sierra.

    variant 0: 4=6 (word list) + ``extra`` (e.g. "@attr 3=3" for Sierra/Aladí);
    variant 1: 4=6 only; variant 2: Use attribute only (1=x), the minimum accepted by any server.
    """
    parts = []
    for k, v in c.items():
        attrs = f"@attr 1={BIB1[k]}"
        if variant <= 1 and k in ("title", "author", "subject", "text"):
            if variant == 0 and extra:
                attrs += f" {extra}"
            attrs += " @attr 4=6"  # word list: more tolerant than exact phrase
        parts.append(f"{attrs} {_pqf_term(v)}")
    if not parts:
        raise ValueError("At least one search criterion is required")
    q = parts[0]
    for p in parts[1:]:
        q = f"@and {q} {p}"
    return q


def to_cql(c: SearchCriteria, indices: dict[str, str]) -> str:
    parts = []
    for k, v in c.items():
        idx = indices.get(k) or indices.get("text")
        if not idx:
            continue
        parts.append(f'{idx}="{v.replace(chr(34), "")}"')
    if not parts:
        raise ValueError("At least one search criterion is required")
    return " and ".join(parts)


# Z39.50 diagnostic codes for "unsupported attribute / invalid combination": worth retrying simpler
ATTRIBUTE_ERROR_CODES = range(113, 124)
