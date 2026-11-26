import json
import xml.etree.ElementTree as ET

import httpx
import pytest

from spain_libraries_mcp import sru
from spain_libraries_mcp.catalogs import DEFAULT_CATALOGS, Catalog, load_catalogs


def test_catalog_opac_url_and_to_public():
    c = Catalog(
        id="x", name="X", scope="A", protocol="z3950",
        user="user", password="secret",
        opac_search="https://example.org/search?q={q}",
    )
    assert c.opac_url("Barberà del Vallès") == "https://example.org/search?q=Barber%C3%A0+del+Vall%C3%A8s"
    pub = c.to_public()
    assert "user" not in pub and "password" not in pub and pub["id"] == "x"

    c2 = Catalog(id="y", name="Y", scope="A", protocol="z3950")
    assert c2.opac_url("quijote") is None


def test_load_catalogs_with_extra_json(tmp_path, monkeypatch):
    extra = [
        {"id": "ccpb", "active": True, "timeout": 30},
        {
            "id": "custom",
            "name": "My Library",
            "scope": "Local",
            "protocol": "sru",
            "sru_url": "https://example.org/sru",
            "regions": ["madrid"],
        },
    ]
    path = tmp_path / "extra.json"
    path.write_text(json.dumps(extra), encoding="utf-8")
    monkeypatch.setenv("SPAIN_LIBRARIES_CATALOGS", str(path))

    cats = load_catalogs()
    assert cats["ccpb"].active is True
    assert cats["ccpb"].timeout == 30
    assert cats["ccpb"].host == "ccpb.mcu.es"  # keeps base fields
    assert cats["custom"].sru_url == "https://example.org/sru"
    # does not mutate DEFAULT_CATALOGS
    orig_ccpb = next(c for c in DEFAULT_CATALOGS if c.id == "ccpb")
    assert orig_ccpb.active is False


def test_sru_parse_response_edge_cases():
    empty = '<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/"><numberOfRecords>0</numberOfRecords></searchRetrieveResponse>'
    r = sru.parse_response(empty)
    assert r.hits == 0 and r.records == []

    bad_hits = '<searchRetrieveResponse><numberOfRecords>N/A</numberOfRecords></searchRetrieveResponse>'
    assert sru.parse_response(bad_hits).hits == 0

    with pytest.raises(ET.ParseError):
        sru.parse_response("<html>not xml")


async def test_sru_search_http_mock():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        captured["ua"] = request.headers.get("user-agent")
        body = """<?xml version="1.0"?>
        <searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
          <numberOfRecords>1</numberOfRecords>
          <records><record><recordData>
            <record xmlns="http://www.loc.gov/MARC21/slim">
              <datafield tag="245"><subfield code="a">Rayuela</subfield></datafield>
            </record>
          </recordData></record></records>
        </searchRetrieveResponse>"""
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, headers={"User-Agent": sru.USER_AGENT}) as client:
        res = await sru.search("https://bne.example/sru", 'alma.title="rayuela"', max_records=3, client=client)
        assert not client.is_closed  # injected client is not closed

    assert res.hits == 1 and len(res.records) == 1
    assert captured["params"]["operation"] == "searchRetrieve"
    assert captured["params"]["version"] == "1.2"
    assert captured["params"]["maximumRecords"] == "3"
    assert captured["params"]["query"] == 'alma.title="rayuela"'
    assert "spain-libraries-mcp" in captured["ua"]


async def test_sru_search_http_error():
    transport = httpx.MockTransport(lambda req: httpx.Response(503, text="Service Unavailable"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await sru.search("https://bne.example/sru", 'alma.title="x"', client=client)
