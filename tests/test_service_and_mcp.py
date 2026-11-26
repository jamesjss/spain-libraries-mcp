import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from spain_libraries_mcp import marc, server, sru, zoom
from spain_libraries_mcp.catalogs import Catalog
from spain_libraries_mcp.queries import SearchCriteria
from spain_libraries_mcp.service import CACHE_TTL, FederatedSearch, normalize_region


def _book(catalog: str, title: str = "El Quijote", holdings=None):
    return marc.Book(catalog=catalog, title=title, isbn=["9788437604947"], holdings=holdings or [])


def test_normalize_region_aliases():
    assert normalize_region("Catalunya") == "cataluna"
    assert normalize_region("Catalonia") == "cataluna"
    assert normalize_region("  Euskadi ") == "pais-vasco"
    assert normalize_region("Basque Country") == "pais-vasco"
    assert normalize_region("Comunidad Valenciana") == "valencia"
    assert normalize_region("Comunitat Valenciana") == "valencia"
    assert normalize_region("Valencian Community") == "valencia"
    assert normalize_region("Illes Balears") == "baleares"
    assert normalize_region("Balearic Islands") == "baleares"
    assert normalize_region("Comunidad de Madrid") == "madrid"
    assert normalize_region("Región de Murcia") == "murcia"
    assert normalize_region("Principado de Asturias") == "asturias"
    assert normalize_region("Castilla y León") == "castilla-y-leon"
    assert normalize_region("Castile and Leon") == "castilla-y-leon"


def test_select_errors_and_inactive():
    cats = {
        "a": Catalog(id="a", name="A", scope="", protocol="z3950", host="h", regions=["madrid"], active=True),
        "b": Catalog(id="b", name="B", scope="", protocol="z3950", host="h", regions=["madrid"], active=False),
    }
    f = FederatedSearch(cats)
    assert [c.id for c in f.select()] == ["a"]
    assert [c.id for c in f.select(include_inactive=True)] == ["a", "b"]
    assert [c.id for c in f.select(ids=["b"])] == ["b"]
    with pytest.raises(ValueError, match="Unknown catalogs"):
        f.select(ids=["nonexistent"])


def test_z3950_retries_variants_and_deduplicates_pqf(monkeypatch):
    cat = Catalog(id="aladi", name="Aladí", scope="", protocol="z3950", host="h", database="b",
                  pqf_extra="@attr 3=3", regions=["cataluna"])
    f = FederatedSearch({"aladi": cat})
    pqfs = []

    def fake_search(host, port, database, pqf, **kw):
        pqfs.append(pqf)
        if len(pqfs) < 3:
            raise zoom.Z3950Error("h:210: Cannot combine (123)", code=123)
        return zoom.ZResult(hits=1, records=[zoom.ZRecord(xml='<record><datafield tag="245"><subfield code="a">Ok</subfield></datafield></record>')])

    monkeypatch.setattr(zoom, "search", fake_search)
    hits, books = f._z3950(cat, SearchCriteria(title="quijote"), 5, False)
    assert hits == 1 and books[0].title == "Ok"
    assert len(pqfs) == 3  # variant 0 -> 1 -> 2

    # ISBN produces the same PQF for all 3 variants: should only try once
    pqfs.clear()

    def always_114(host, port, database, pqf, **kw):
        pqfs.append(pqf)
        raise zoom.Z3950Error("h:210: Unsupported (114)", code=114)

    monkeypatch.setattr(zoom, "search", always_114)
    with pytest.raises(zoom.Z3950Error):
        f._z3950(cat, SearchCriteria(isbn="9788437604947"), 5, False)
    assert len(pqfs) == 1


def test_z3950_opac_fallback_to_usmarc(monkeypatch):
    cat = Catalog(id="c", name="C", scope="", protocol="z3950", host="h", database="b", regions=["madrid"])
    f = FederatedSearch({"c": cat})
    calls = []

    def fake_search(host, port, database, pqf, *, syntax, **kw):
        calls.append((syntax, pqf))
        if syntax == "opac":
            raise zoom.Z3950Error("h:210: Record syntax not supported (238)", code=238)
        return zoom.ZResult(hits=1, records=[zoom.ZRecord(xml='<record><datafield tag="245"><subfield code="a">USMARC</subfield></datafield></record>')])

    monkeypatch.setattr(zoom, "search", fake_search)
    hits, books = f._z3950(cat, SearchCriteria(title="quijote"), 5, True)
    assert hits == 1 and books[0].title == "USMARC"
    assert [s for s, _ in calls] == ["opac", "usmarc"]


async def test_sru_respects_catalog_timeout(monkeypatch):
    cat = Catalog(id="bne", name="BNE", scope="", protocol="sru", sru_url="https://bne.example/sru",
                  sru_indices={"title": "alma.title"}, timeout=45, regions=["madrid"])
    f = FederatedSearch({"bne": cat}, timeout=10)
    seen = {}

    async def fake_sru(url, cql, *, max_records, timeout):
        seen["timeout"] = timeout
        return sru.SruResult(hits=1, records=['<record><datafield tag="245"><subfield code="a">Rayuela</subfield></datafield></record>'])

    monkeypatch.setattr(sru, "search", fake_sru)
    r = await f.search(SearchCriteria(title="rayuela"))
    assert seen["timeout"] == 45
    assert r["total_found"] == 1


async def test_error_isolation_timeout_and_yaz(monkeypatch):
    cats = {
        "slow": Catalog(id="slow", name="Slow", scope="", protocol="z3950", host="h", timeout=0, regions=["madrid"]),
        "noyaz": Catalog(id="noyaz", name="NoYAZ", scope="", protocol="z3950", host="h", regions=["madrid"]),
        "ok": Catalog(id="ok", name="OK", scope="", protocol="z3950", host="h", regions=["madrid"]),
    }
    f = FederatedSearch(cats, timeout=1)

    def fake_z3950(cat, c, n, with_h):
        if cat.id == "noyaz":
            raise zoom.YazNotAvailable("libyaz not found")
        return 1, [_book("ok")]

    monkeypatch.setattr(f, "_z3950", fake_z3950)
    orig_to_thread = asyncio.to_thread

    async def fake_to_thread(fn, cat, *args):
        if cat.id == "slow":
            raise asyncio.TimeoutError()
        return await orig_to_thread(fn, cat, *args)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    r = await f.search(SearchCriteria(title="quijote"))
    by_id = {x["catalog"]: x for x in r["results"]}
    assert "No response" in by_id["slow"]["error"]
    assert "libyaz" in by_id["noyaz"]["error"]
    assert by_id["ok"]["total_found"] == 1
    # errors are not cached
    assert all(k[0] == "ok" for k in f._cache)


async def test_cache_immutability_and_ttl(monkeypatch):
    cat = Catalog(id="c", name="C", scope="", protocol="z3950", host="h", regions=["madrid"])
    f = FederatedSearch({"c": cat})
    calls = 0
    clock = [1000.0]

    monkeypatch.setattr("spain_libraries_mcp.service.time.monotonic", lambda: clock[0])

    def fake_z3950(cat, c, n, with_h):
        nonlocal calls
        calls += 1
        return 1, [_book("c")]  # no holdings

    monkeypatch.setattr(f, "_z3950", fake_z3950)
    r1 = await f.search(SearchCriteria(title="quijote"))
    # Must not inject "holdings": [] when the book had no holdings
    assert "holdings" not in r1["results"][0]["books"][0]
    # Mutating the returned dict must not corrupt the cache
    r1["results"][0]["books"][0]["title"] = "MUTATED"

    r2 = await f.search(SearchCriteria(title="quijote"))
    assert calls == 1
    assert r2["results"][0]["books"][0]["title"] == "El Quijote"

    # After TTL expires, queries again
    clock[0] += CACHE_TTL + 1
    await f.search(SearchCriteria(title="quijote"))
    assert calls == 2


async def test_locate_without_holdings_and_check(monkeypatch):
    cats = {
        "no_holdings": Catalog(id="no_holdings", name="NoHoldings", scope="", protocol="z3950", host="h",
                               opac_search="https://opac.example/?q={q}", regions=["madrid"]),
        "inactive": Catalog(id="inactive", name="Inactive", scope="", protocol="z3950", host="h",
                            regions=["madrid"], active=False),
    }
    f = FederatedSearch(cats)

    def fake_z3950(cat, c, n, with_h):
        if cat.id == "inactive":
            raise RuntimeError("down")
        return 3, [_book("no_holdings")]

    monkeypatch.setattr(f, "_z3950", fake_z3950)
    loc = await f.locate(SearchCriteria(title="quijote"))
    assert loc["holdings_in_catalogs"] == 0
    assert loc["catalogs_without_holdings_data"][0]["catalog"] == "no_holdings"
    assert loc["catalogs_without_holdings_data"][0]["found"] == 3

    status = await f.check(include_inactive=True)
    by_id = {x["catalog"]: x for x in status}
    assert by_id["no_holdings"]["ok"] is True and by_id["no_holdings"]["active"] is True
    assert by_id["inactive"]["ok"] is False and by_id["inactive"]["active"] is False


async def test_mcp_tools_expose_errors_as_toolerror(monkeypatch):
    cat = Catalog(id="test", name="Test", scope="", protocol="z3950", host="h",
                  user="u", password="secret", regions=["madrid"])
    monkeypatch.setattr(server, "_fed", FederatedSearch({"test": cat}))

    # list_catalogs never exposes credentials
    listing = server.list_catalogs()
    assert len(listing) == 1 and "password" not in listing[0] and "user" not in listing[0]

    # empty criteria -> ToolError
    with pytest.raises(ToolError, match="Provide at least"):
        await server.search_books()
    with pytest.raises(ToolError, match="Provide at least"):
        await server.locate_holdings()

    # unknown catalog -> ToolError
    with pytest.raises(ToolError, match="Unknown catalogs"):
        await server.search_books(title="quijote", catalogs=["does_not_exist"])
    with pytest.raises(ToolError, match="Unknown catalogs"):
        await server.locate_holdings(title="quijote", catalogs=["does_not_exist"])

    # geographic errors -> ToolError
    with pytest.raises(ToolError, match="requires"):
        await server.search_books(title="quijote", radius_km=5)
    with pytest.raises(ToolError, match="greater than 0"):
        await server.locate_holdings(title="quijote", near="Barcelona", radius_km=0)
    with pytest.raises(ToolError, match="out of range"):
        await server.locate_holdings(title="quijote", near="95.0,2.0")


def test_server_main_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))

    monkeypatch.setattr("sys.argv", ["spain-libraries-mcp"])
    server.main()
    assert calls[-1] == (("stdio",), {})

    monkeypatch.setattr("sys.argv", ["spain-libraries-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000"])
    server.main()
    assert calls[-1] == (("streamable-http",), {"host": "0.0.0.0", "port": 9000})
