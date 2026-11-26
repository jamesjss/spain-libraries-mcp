"""Geolocation: municipalities, holding placement, and proximity sorting.

A catalog only says "this holding is at library X". To sort by proximity we need to know
which municipality X belongs to and where that municipality is located. This is resolved in two steps:

1. Optional directory (`libraries.csv`): key (code or name) -> municipality. Most reliable.
2. If no entry matches, we search for a known municipality name within the library text
   ("Biblioteca Central de Sabadell"). This is a heuristic and marked `location_source: "name"`.

Holdings that cannot be located are never silently dropped: they are reported separately.
"""

from __future__ import annotations

import csv
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).parent / "data"
_ARTICLES = ("l'", "el ", "la ", "els ", "les ")
# Phrases that contain a municipality name but do not indicate where the library is located.
_NOISE_PATTERNS = [  # applied in order: "diputació de X" first, then the rest
    re.compile(r"\b(diputacio|provincia|consell comarcal|comarca)\s+(de|del)\s+(la\s+|l\s+)?\w+"),
    re.compile(r"\b(xarxa|red)\s+de\s+biblioteques(\s+\w+)?"),
]
_COORD = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[·'’`\-_,.()/]", " ", s)
    return " ".join(s.split())


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, a)))


def _canonical_name(name: str) -> str:
    """'Hospitalet de Llobregat, l'' -> 'L'Hospitalet de Llobregat' (Generalitat format)."""
    m = re.match(r"^(.+?),\s*(l'|el|la|els|les)\s*$", name.strip(), re.I)
    if not m:
        return name.strip()
    base, art = m.group(1), m.group(2)
    art = art[0].upper() + art[1:]
    return f"{art}{base}" if art.endswith("'") else f"{art} {base}"


@dataclass(frozen=True)
class Municipality:
    name: str
    province: str
    county: str
    region: str
    lat: float
    lon: float
    approx: bool = False


@dataclass
class Origin:
    label: str
    lat: float
    lon: float
    municipality: Municipality | None = None


@dataclass
class GeoFilter:
    """Geographic criteria for a query. Empty = no geographic filtering or sorting."""
    origin: Origin | None = None
    radius_km: float | None = None
    municipality: Municipality | None = None
    province: str | None = None  # normalized
    county: str | None = None  # normalized (Spanish/Catalan comarca)

    @property
    def restricts(self) -> bool:
        return bool(self.radius_km or self.municipality or self.province or self.county)

    @property
    def active(self) -> bool:
        return self.restricts or self.origin is not None

    @property
    def region(self) -> str | None:
        for m in (self.municipality, self.origin.municipality if self.origin else None):
            if m:
                return m.region
        return None


@dataclass
class Geo:
    municipalities: list[Municipality] = field(default_factory=list)
    directory: dict[tuple[str, str], str] = field(default_factory=dict)  # (catalog|"", key) -> municipality

    def __post_init__(self) -> None:
        self._idx: dict[str, Municipality] = {}
        for m in self.municipalities:
            n = norm(m.name)
            self._idx[n] = m
            for art in _ARTICLES:  # "l'hospitalet de llobregat" also indexed as "hospitalet de llobregat"
                if n.startswith(norm(art)) and len(n) > len(norm(art)) + 3:
                    self._idx.setdefault(n[len(norm(art)):].strip(), m)
        keys = sorted((k for k in self._idx if len(k) >= 4), key=len, reverse=True)
        self._re = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b") if keys else None

    # ---------- loading ----------
    @classmethod
    def load(cls) -> "Geo":
        mun_path = Path(os.environ.get("SPAIN_LIBRARIES_MUNICIPALITIES", DATA / "municipalities.csv"))
        dir_path = Path(os.environ.get("SPAIN_LIBRARIES_DIRECTORY", DATA / "libraries.csv"))
        return cls(_read_municipalities(mun_path), _read_directory(dir_path))

    # ---------- lookup ----------
    def municipality(self, text: str) -> Municipality:
        n = norm(text)
        if not n:
            raise ValueError("Empty municipality")
        if n in self._idx:
            return self._idx[n]
        cands = {id(m): m for k, m in self._idx.items() if k.startswith(n)}
        if not cands:
            cands = {id(m): m for k, m in self._idx.items() if n in k}
        if len(cands) == 1:
            return next(iter(cands.values()))
        if cands:
            names = sorted(m.name for m in cands.values())[:8]
            raise ValueError(f"'{text}' is ambiguous: {', '.join(names)}")
        raise ValueError(
            f"Municipality '{text}' not found among the {len(self.municipalities)} known entries. "
            "Use coordinates ('41.39,2.17') or expand the list with spain-libraries-update-municipalities")

    def origin(self, text: str) -> Origin:
        c = _COORD.match(text)
        if c:
            lat, lon = float(c.group(1)), float(c.group(2))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f"Coordinates out of range: '{text}' (lat -90..90, lon -180..180)")
            return Origin(f"{c.group(1)},{c.group(2)}", lat, lon)
        m = self.municipality(text)
        return Origin(m.name, m.lat, m.lon, m)

    def filter(self, *, near: str | None = None, radius_km: float | None = None, municipality: str | None = None,
               province: str | None = None, county: str | None = None) -> GeoFilter:
        if radius_km is not None and not near:
            raise ValueError("`radius_km` requires `near`")
        if radius_km is not None and radius_km <= 0:
            raise ValueError("`radius_km` must be greater than 0")
        return GeoFilter(
            origin=self.origin(near) if near else None,
            radius_km=radius_km,
            municipality=self.municipality(municipality) if municipality else None,
            province=norm(province) or None if province else None,
            county=norm(county) or None if county else None,
        )

    def locate(self, catalog: str, holding: dict) -> tuple[Municipality | None, str | None]:
        texts = [t for t in (holding.get("library"), holding.get("location")) if t]
        for t in texts:
            name = self.directory.get((catalog, norm(t))) or self.directory.get(("", norm(t)))
            if name:
                try:
                    return self.municipality(name), "directory"
                except ValueError:
                    pass
        if self._re:
            for t in texts:
                cleaned = norm(t)
                for pattern in _NOISE_PATTERNS:
                    cleaned = pattern.sub(" ", cleaned)
                m = self._re.search(cleaned)
                if m:
                    return self._idx[m.group(1)], "name"
        return None, None

    # ---------- apply to holdings list ----------
    def annotate(self, catalog: str, holdings: list[dict], geo_filter: GeoFilter) -> None:
        """Add municipality, county, distance_km, and location_source to each holding (dict) in place."""
        for h in holdings:
            m, via = self.locate(catalog, h)
            if not m:
                continue
            h["municipality"], h["county"], h["location_source"] = m.name, m.county, via
            h["_m"] = m
            if geo_filter.origin:
                h["distance_km"] = round(
                    haversine_km(geo_filter.origin.lat, geo_filter.origin.lon, m.lat, m.lon), 1
                )

    def matches(self, holding: dict, geo_filter: GeoFilter) -> bool:
        m: Municipality | None = holding.get("_m")
        if m is None:
            return not geo_filter.restricts
        if geo_filter.municipality and m != geo_filter.municipality:
            return False
        if geo_filter.province and norm(m.province) != geo_filter.province:
            return False
        if geo_filter.county and norm(m.county) != geo_filter.county:
            return False
        if geo_filter.radius_km and holding.get("distance_km", math.inf) > geo_filter.radius_km:
            return False
        return True


def sort_key(holding: dict) -> tuple:
    """Closest first; at equal distance, available before checked out; unlocated last."""
    d = holding.get("distance_km")
    return (d is None, d if d is not None else 0.0, holding.get("status") != "available")


def clean_holding(holding: dict) -> dict:
    return {k: v for k, v in holding.items() if not k.startswith("_")}


def _read_municipalities(path: Path) -> list[Municipality]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8", newline="") as fh:
        rows = (line for line in fh if line.strip() and not line.lstrip().startswith("#"))
        for r in csv.DictReader(rows):
            try:
                out.append(Municipality(
                    _canonical_name(r["name"]), r.get("province", ""), r.get("county", ""),
                    r.get("region", ""), float(r["lat"]), float(r["lon"]),
                    (r.get("approx") or "0").strip() in ("1", "true", "True"),
                ))
            except (KeyError, ValueError):
                continue
    return out


def _read_directory(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    d = {}
    with open(path, encoding="utf-8", newline="") as fh:
        rows = (line for line in fh if line.strip() and not line.lstrip().startswith("#"))
        for r in csv.DictReader(rows):
            if r.get("key") and r.get("municipality"):
                d[((r.get("catalog") or "").strip(), norm(r["key"]))] = r["municipality"].strip()
    return d
