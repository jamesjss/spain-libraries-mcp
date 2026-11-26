"""Federated search: queries multiple catalogs in parallel and merges results."""

from __future__ import annotations

import asyncio
import copy
import time
import unicodedata
from dataclasses import dataclass

from . import marc, sru, zoom
from .catalogs import Catalog, load_catalogs
from .geo import Geo, GeoFilter, clean_holding, sort_key
from .queries import ATTRIBUTE_ERROR_CODES, SearchCriteria, to_cql, to_pqf

CACHE_TTL = 300  # seconds; avoids repeating the same query against public servers
MAX_PER_CATALOG = 20


def normalize_region(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()
    aliases = {
        "andalusia": "andalucia",
        "catalonia": "cataluna",
        "catalunya": "cataluna",
        "basque-country": "pais-vasco",
        "euskadi": "pais-vasco",
        "valencian-community": "valencia",
        "comunidad-valenciana": "valencia",
        "comunitat-valenciana": "valencia",
        "balearic-islands": "baleares",
        "illes-balears": "baleares",
        "islas-baleares": "baleares",
        "canary-islands": "canarias",
        "islas-canarias": "canarias",
        "castile-and-leon": "castilla-y-leon",
        "community-of-madrid": "madrid",
        "comunidad-de-madrid": "madrid",
        "region-of-murcia": "murcia",
        "region-de-murcia": "murcia",
        "principality-of-asturias": "asturias",
        "principado-de-asturias": "asturias",
        "navarre": "navarra",
    }
    s = "-".join(s.replace(",", " ").split())
    return aliases.get(s, s)


@dataclass
class FederatedSearch:
    catalogs: dict[str, Catalog]
    timeout: int = 20
    geo: Geo | None = None

    def __post_init__(self) -> None:
        if self.geo is None:
            self.geo = Geo.load()
        self._sems = {cid: asyncio.Semaphore(2) for cid in self.catalogs}  # politeness limit per server
        self._cache: dict[tuple, tuple[float, dict]] = {}

    @classmethod
    def from_env(cls) -> "FederatedSearch":
        return cls(load_catalogs())

    # ---------- selection ----------
    def select(self, ids: list[str] | None = None, region: str | None = None,
               include_inactive: bool = False) -> list[Catalog]:
        if ids:
            unknown = [i for i in ids if i not in self.catalogs]
            if unknown:
                raise ValueError(f"Unknown catalogs: {unknown}. Use list_catalogs.")
            return [self.catalogs[i] for i in ids]
        cats = [c for c in self.catalogs.values() if c.active or include_inactive]
        if region:
            r = normalize_region(region)
            cats = [c for c in cats if r in c.regions]
        return cats

    # ---------- search ----------
    async def search(self, criteria: SearchCriteria, *, ids: list[str] | None = None, region: str | None = None,
                     max_per_catalog: int = 5, with_holdings: bool = False,
                     geo_filter: GeoFilter | None = None) -> dict:
        r = await self._search(criteria, ids=ids, region=region, max_per_catalog=max_per_catalog,
                               with_holdings=with_holdings, geo_filter=geo_filter)
        for res in r["results"]:
            for book in res.get("books", []):
                if "holdings" in book:
                    book["holdings"] = [clean_holding(h) for h in book["holdings"]]
                for k in [k for k in book if k.startswith("_")]:
                    del book[k]
        return r

    async def _search(self, criteria: SearchCriteria, *, ids, region, max_per_catalog: int, with_holdings: bool,
                      geo_filter: GeoFilter | None) -> dict:
        if criteria.is_empty():
            raise ValueError("Provide at least title, author, ISBN, subject, or text")
        n = max(1, min(max_per_catalog, MAX_PER_CATALOG))
        if geo_filter and geo_filter.active and not ids and not region:
            region = geo_filter.region  # catalogs for the municipality's region (+ national ones)
        cats = self.select(ids, region)
        results = copy.deepcopy(
            list(await asyncio.gather(*(self._search_catalog(c, criteria, n, with_holdings) for c in cats)))
        )  # cached entries must never be mutated by geo annotations or callers
        if geo_filter and geo_filter.active:
            for res in results:
                for book in res.get("books", []):
                    self._apply_geo(res["catalog"], book, geo_filter)
        total = sum(r.get("total_found", 0) for r in results)
        out = {
            "query": dict(criteria.items()),
            "catalogs_queried": len(cats),
            "total_found": total,
            "results": results,
        }
        if geo_filter and geo_filter.active:
            out["geo"] = {
                **({"near": geo_filter.origin.label} if geo_filter.origin else {}),
                **({"radius_km": geo_filter.radius_km} if geo_filter.radius_km else {}),
                **({"municipality": geo_filter.municipality.name} if geo_filter.municipality else {}),
                **({"province": geo_filter.province} if geo_filter.province else {}),
                **({"county": geo_filter.county} if geo_filter.county else {}),
            }
        return out

    def _apply_geo(self, catalog: str, book: dict, geo_filter: GeoFilter) -> None:
        holdings = book.get("holdings", [])
        book["_n_holdings"] = len(holdings)
        self.geo.annotate(catalog, holdings, geo_filter)
        book["_unlocated"] = [h for h in holdings if "_m" not in h]
        kept = [h for h in holdings if self.geo.matches(h, geo_filter)]
        book["holdings"] = sorted(kept, key=sort_key)
        if len(kept) != len(holdings):
            book["holdings_outside_filter"] = len(holdings) - len(kept)

    async def _search_catalog(self, cat: Catalog, c: SearchCriteria, n: int, with_holdings: bool) -> dict:
        key = (cat.id, tuple(c.items()), n, with_holdings)
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL:
            return hit[1]
        base = {"catalog": cat.id, "name": cat.name}
        url = cat.opac_url(c.summary())
        if url:
            base["opac_search_url"] = url
        t0 = time.monotonic()
        try:
            async with self._sems[cat.id]:
                if cat.protocol == "sru":
                    hits, books = await self._sru(cat, c, n)
                else:
                    hits, books = await asyncio.wait_for(
                        asyncio.to_thread(self._z3950, cat, c, n, with_holdings),
                        (cat.timeout or self.timeout) + 5,
                    )
            out = {**base, "total_found": hits, "books": [b.to_dict() for b in books]}
        except zoom.YazNotAvailable as e:
            out = {**base, "error": str(e)}
        except asyncio.TimeoutError:
            out = {**base, "error": f"No response within {(cat.timeout or self.timeout) + 5}s"}
        except Exception as e:  # noqa: BLE001 - a failing catalog must not break the whole search
            out = {**base, "error": f"{type(e).__name__}: {e}"}
        out["ms"] = int((time.monotonic() - t0) * 1000)
        if "error" not in out:
            self._cache[key] = (time.monotonic(), out)
        return out

    @staticmethod
    def _is_attribute_error(e: zoom.Z3950Error) -> bool:
        if e.code:
            return e.code in ATTRIBUTE_ERROR_CODES
        return any(f"({code})" in str(e) for code in ATTRIBUTE_ERROR_CODES)

    def _z3950(self, cat: Catalog, c: SearchCriteria, n: int, with_holdings: bool) -> tuple[int, list[marc.Book]]:
        kw = dict(max_records=n, charset=cat.charset, user=cat.user, password=cat.password,
                  timeout=cat.timeout or self.timeout)
        res, used_opac, last_err, seen = None, False, None, set()
        # If the server rejects the attribute combination, retry with simpler queries.
        for variant in (0, 1, 2):
            pqf = to_pqf(c, variant, cat.pqf_extra)
            if pqf in seen:
                continue
            seen.add(pqf)
            try:
                res, used_opac = self._z3950_once(cat, pqf, with_holdings, kw)
                break
            except zoom.Z3950Error as e:
                last_err = e
                if not self._is_attribute_error(e):
                    raise
        if res is None:
            raise last_err
        books = []
        for r in res.records:
            xml = r.xml
            if not xml and r.opac:
                xml = r.opac
            book = marc.parse_marcxml(xml, cat.id, cat.holdings_profile) if xml else None
            if not book:
                continue
            if used_opac and r.opac:
                op = marc.opac_holdings(r.opac)
                if op:
                    book.holdings = op + [h for h in book.holdings if h.source != "opac"]
            books.append(book)
        return res.hits, books

    def _z3950_once(self, cat: Catalog, pqf: str, with_holdings: bool, kw: dict):
        if with_holdings or cat.syntax == "opac":
            try:
                return zoom.search(cat.host, cat.port, cat.database, pqf, syntax="opac", **kw), True
            except zoom.Z3950Error as e:
                if self._is_attribute_error(e):
                    raise  # query attribute issue, not OPAC syntax issue
        return zoom.search(cat.host, cat.port, cat.database, pqf, syntax="usmarc", **kw), False

    async def _sru(self, cat: Catalog, c: SearchCriteria, n: int) -> tuple[int, list[marc.Book]]:
        res = await sru.search(cat.sru_url, to_cql(c, cat.sru_indices), max_records=n,
                               timeout=cat.timeout or self.timeout)
        books = [b for x in res.records if (b := marc.parse_marcxml(x, cat.id, cat.holdings_profile))]
        return res.hits, books

    # ---------- aggregated holdings lookup ----------
    async def locate(self, criteria: SearchCriteria, *, ids=None, region=None, max_per_catalog: int = 5,
                     geo_filter: GeoFilter | None = None, available_only: bool = False) -> dict:
        r = await self._search(criteria, ids=ids, region=region, max_per_catalog=max_per_catalog,
                               with_holdings=True, geo_filter=geo_filter)
        locations: list[dict] = []
        unlocated: dict[str, int] = {}
        total_holdings = outside = 0
        no_data = []
        for res in r["results"]:
            has_holdings = False
            for book in res.get("books", []):
                n_orig = book.get("_n_holdings", len(book.get("holdings", [])))
                has_holdings = has_holdings or n_orig > 0
                total_holdings += n_orig
                outside += book.get("holdings_outside_filter", 0)
                for h in book.get("_unlocated", []):
                    name = h.get("library") or h.get("location") or "(unnamed)"
                    unlocated[name] = unlocated.get(name, 0) + 1
                for h in book.get("holdings", []):
                    if available_only and h.get("status") != "available":
                        continue
                    locations.append({
                        "catalog": res["catalog"],
                        "title": book.get("title"),
                        "isbn": (book.get("isbn") or [None])[0],
                        **{k: h[k] for k in ("library", "municipality", "county", "distance_km", "location",
                                             "call_number", "status", "available", "total", "location_source")
                           if h.get(k) is not None},
                    })
            if res.get("total_found") and not has_holdings and "error" not in res:
                no_data.append({"catalog": res["catalog"], "opac_search_url": res.get("opac_search_url"),
                                "found": res.get("total_found", 0)})
        if geo_filter and geo_filter.origin:
            locations.sort(key=sort_key)  # global proximity order across catalogs
        available = [loc for loc in locations if loc.get("status") == "available"]
        out = {
            "query": r["query"],
            **({"geo": r["geo"]} if "geo" in r else {}),
            "holdings_in_catalogs": total_holdings,
            "holdings_shown": len(locations),
            "holdings_available_now": len(available),
            "locations": locations,
            "catalogs_without_holdings_data": no_data,
            "errors": [{"catalog": x["catalog"], "error": x["error"]} for x in r["results"] if "error" in x],
        }
        if geo_filter and geo_filter.active:
            if outside:
                out["holdings_outside_filter"] = outside
            if unlocated:
                out["unlocated_libraries"] = dict(sorted(unlocated.items(), key=lambda kv: -kv[1])[:15])
                out["notice"] = ("Some libraries could not be matched to a municipality"
                                 + (" and were excluded by the filter" if geo_filter.restricts else " and are listed last")
                                 + ". Add them to data/libraries.csv (key, municipality).")
        return out

    async def check(self, include_inactive: bool = True) -> list[dict]:
        probe = SearchCriteria(title="quijote")
        cats = self.select(include_inactive=include_inactive)
        res = await asyncio.gather(*(self._search_catalog(c, probe, 1, False) for c in cats))
        return [{"catalog": r["catalog"], "ok": "error" not in r, "ms": r["ms"],
                 "test_records": r.get("total_found"), "error": r.get("error"),
                 "active": self.catalogs[r["catalog"]].active,
                 "verified_in_docs": self.catalogs[r["catalog"]].verified} for r in res]
