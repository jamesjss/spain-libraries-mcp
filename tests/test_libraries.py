import shutil
import socket
import subprocess
import time

import pytest

from spain_libraries_mcp import marc, sru, zoom
from spain_libraries_mcp.catalogs import Catalog, load_catalogs
from spain_libraries_mcp.queries import SearchCriteria, to_cql, to_pqf
from spain_libraries_mcp.service import FederatedSearch, normalize_region

KOHA = """<record xmlns="http://www.loc.gov/MARC21/slim">
<leader>00000nam a2200000 a 4500</leader>
<controlfield tag="001">12345</controlfield>
<controlfield tag="008">200101s2019    sp            000 1 spa d</controlfield>
<datafield tag="020" ind1=" " ind2=" "><subfield code="a">978-84-376-0494-7 (rúst.)</subfield></datafield>
<datafield tag="100" ind1="1" ind2=" "><subfield code="a">Cervantes Saavedra, Miguel de,</subfield></datafield>
<datafield tag="245" ind1="1" ind2="0"><subfield code="a">Don Quijote de la Mancha /</subfield></datafield>
<datafield tag="264" ind1=" " ind2="1"><subfield code="b">Cátedra,</subfield><subfield code="c">2019.</subfield></datafield>
<datafield tag="952" ind1=" " ind2=" "><subfield code="a">BPLU</subfield><subfield code="b">BPLU</subfield><subfield code="o">N CER qui</subfield><subfield code="7">0</subfield></datafield>
<datafield tag="952" ind1=" " ind2=" "><subfield code="a">BPOU</subfield><subfield code="b">BPOU</subfield><subfield code="q">2026-12-01</subfield></datafield>
</record>"""

ALMA = """<record xmlns="http://www.loc.gov/MARC21/slim"><leader>x</leader>
<controlfield tag="001">99100</controlfield>
<datafield tag="245" ind1="0" ind2="0"><subfield code="a">Rayuela</subfield></datafield>
<datafield tag="AVA" ind1=" " ind2=" "><subfield code="b">BNE</subfield><subfield code="q">Sede Recoletos</subfield>
<subfield code="d">VC/123</subfield><subfield code="e">available</subfield><subfield code="f">3</subfield><subfield code="g">1</subfield></datafield>
</record>"""

SRU_RESP = f"""<?xml version="1.0"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
<version>1.2</version><numberOfRecords>42</numberOfRecords>
<records><record><recordSchema>marcxml</recordSchema><recordPacking>xml</recordPacking>
<recordData>{ALMA}</recordData><recordPosition>1</recordPosition></record></records>
</searchRetrieveResponse>"""


def test_pqf_and_cql():
    c = SearchCriteria(title='El "Quijote"', author="Cervantes", isbn="978-84-376-0494-7")
    assert to_pqf(c) == ('@and @and @attr 1=7 "9788437604947" @attr 1=4 @attr 4=6 "El \\"Quijote\\"" '
                         '@attr 1=1003 @attr 4=6 "Cervantes"')
    assert to_cql(SearchCriteria(title="rayuela"), {"title": "alma.title"}) == 'alma.title="rayuela"'
    with pytest.raises(ValueError):
        to_pqf(SearchCriteria())


def test_koha_holdings():
    book = marc.parse_marcxml(KOHA, "galicia", "koha")
    assert book.title == "Don Quijote de la Mancha"
    assert book.author == "Cervantes Saavedra, Miguel de"
    assert book.publisher == "Cátedra" and book.year == "2019" and book.language == "spa"
    assert book.isbn == ["9788437604947"]
    assert [(h.library, h.status) for h in book.holdings] == [("BPLU", "available"), ("BPOU", "checked_out")]


def test_alma_and_sru():
    r = sru.parse_response(SRU_RESP)
    assert r.hits == 42 and len(r.records) == 1
    book = marc.parse_marcxml(r.records[0], "bne", "alma")
    h = book.holdings[0]
    assert (h.library, h.status, h.total, h.available) == ("Sede Recoletos", "available", 3, 2)


def test_sru_diagnostic():
    with pytest.raises(RuntimeError):
        sru.parse_response('<r xmlns:d="http://www.loc.gov/zing/srw/diagnostic/"><d:diagnostic>'
                           '<d:message>Bad query</d:message></d:diagnostic></r>')


def test_regions_and_catalogs():
    assert normalize_region("Cataluña") == "cataluna"
    assert normalize_region("Catalonia") == "cataluna"
    assert normalize_region("Euskadi") == "pais-vasco"
    assert normalize_region("Basque Country") == "pais-vasco"
    cats = load_catalogs()
    assert {"ccbip", "bne", "rebiun", "aladi", "galicia", "euskadi", "csic"} <= set(cats)
    f = FederatedSearch(cats)
    ids = {c.id for c in f.select(region="Galicia")}
    assert "galicia" in ids and "aladi" not in ids and "ccbip" in ids
    assert "password" not in cats["euskadi"].to_public()


# ---------- Integration with a real Z39.50 server (yaz-ztest) ----------

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def ztest():
    if not shutil.which("yaz-ztest") or not zoom.yaz_available():
        pytest.skip("yaz-ztest / libyaz not installed")
    port = _free_port()
    proc = subprocess.Popen(["yaz-ztest", "-l", "/dev/null", f"tcp:127.0.0.1:{port}"])
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.1).close()
            break
        except OSError:
            time.sleep(0.1)
    yield port
    proc.terminate()


def test_zoom_marc(ztest):
    r = zoom.search("127.0.0.1", ztest, "Default", '@attr 1=4 "computer"', max_records=3)
    assert r.hits > 0 and len(r.records) == 3
    assert r.records[0].raw and "<record" in r.records[0].xml


def test_zoom_error(ztest):
    with pytest.raises(zoom.Z3950Error):
        zoom.search("127.0.0.1", _free_port(), "Default", "@attr 1=4 x", timeout=2)


async def test_federated_search_against_ztest(ztest):
    cat = Catalog(id="test", name="ztest", scope="tests", protocol="z3950", host="127.0.0.1",
                  port=ztest, database="Default", regions=["madrid"])
    down = Catalog(id="down", name="down", scope="", protocol="z3950", host="127.0.0.1",
                   port=_free_port(), database="x", regions=["madrid"])
    f = FederatedSearch({"test": cat, "down": down}, timeout=3)
    res = await f.search(SearchCriteria(title="computer"), max_per_catalog=2)
    by_id = {r["catalog"]: r for r in res["results"]}
    assert by_id["test"]["total_found"] > 0 and len(by_id["test"]["books"]) == 2
    assert "error" in by_id["down"]  # a down catalog does not break the rest

    loc = await f.locate(SearchCriteria(title="computer"), ids=["test"], max_per_catalog=1)
    assert loc["holdings_available_now"] >= 1  # holdings via OPAC syntax
    assert loc["locations"][0]["status"] == "available"


async def test_mcp_tools(ztest, monkeypatch):
    from spain_libraries_mcp import server
    cat = Catalog(id="test", name="ztest", scope="", protocol="z3950", host="127.0.0.1",
                  port=ztest, database="Default", regions=["madrid"])
    monkeypatch.setattr(server, "_fed", FederatedSearch({"test": cat}, timeout=3))
    names = {t.name for t in await server.mcp.list_tools()}
    assert names == {"list_catalogs", "search_books", "locate_holdings", "check_catalogs"}
    out = await server.search_books(title="computer", max_per_catalog=1)
    assert out["total_found"] > 0
