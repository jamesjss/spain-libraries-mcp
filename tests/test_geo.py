import pytest

from spain_libraries_mcp import marc, updater
from spain_libraries_mcp.catalogs import Catalog
from spain_libraries_mcp.geo import Geo, haversine_km, norm
from spain_libraries_mcp.queries import SearchCriteria
from spain_libraries_mcp.service import FederatedSearch


@pytest.fixture(scope="module")
def geo():
    return Geo.load()


def test_norm_and_haversine():
    assert norm("Barberà del Vallès") == "barbera del valles"
    assert norm("L'Hospitalet") == "l hospitalet"
    # Barcelona - Madrid ≈ 505 km
    assert 495 < haversine_km(41.3874, 2.1686, 40.4168, -3.7038) < 515


def test_origin_without_accents_and_prefix(geo):
    assert geo.origin("Barbera del Valles").municipality.name == "Barberà del Vallès"
    assert geo.origin("barbera").municipality.name == "Barberà del Vallès"
    assert geo.origin("Hospitalet").municipality.name == "L'Hospitalet de Llobregat"
    o = geo.origin("41.39,2.17")
    assert (o.lat, o.lon) == (41.39, 2.17) and o.municipality is None


def test_origin_errors(geo):
    with pytest.raises(ValueError, match="ambiguous"):
        geo.municipality("Sant")
    with pytest.raises(ValueError, match="not found"):
        geo.municipality("Atlantis")
    with pytest.raises(ValueError, match="requires"):
        geo.filter(radius_km=5)


def test_locate_by_name_and_directory():
    g = Geo.load()
    g.directory[("aladi", norm("BIB 123"))] = "Ripollet"
    assert g.locate("aladi", {"library": "BIB 123"}) == (g.municipality("Ripollet"), "directory")
    m, via = g.locate("aladi", {"library": "Biblioteca Central de Barberà del Vallès"})
    assert (m.name, via) == ("Barberà del Vallès", "name")
    # "Diputació de Barcelona" must not place the library in Barcelona
    assert g.locate("aladi", {"library": "Xarxa de la Diputació de Barcelona"}) == (None, None)
    assert g.locate("aladi", {"library": "Biblioteca Desconocida"}) == (None, None)


def test_canonical_generalitat_name():
    from spain_libraries_mcp.geo import _canonical_name
    assert _canonical_name("Hospitalet de Llobregat, l'") == "L'Hospitalet de Llobregat"
    assert _canonical_name("Pobla de Segur, la") == "La Pobla de Segur"


# ---------- service integration (offline) ----------

def _book(catalog, *holdings):
    return marc.Book(catalog=catalog, title="La sombra del viento", isbn=["9788408172178"],
                     holdings=[marc.Holding(library=b, status=s, source="test") for b, s in holdings])


@pytest.fixture
def fed(monkeypatch):
    cats = {
        "aladi": Catalog(id="aladi", name="Aladí", scope="", protocol="z3950", host="x", regions=["cataluna"]),
        "ccbip": Catalog(id="ccbip", name="CCBIP", scope="", protocol="z3950", host="x", regions=["cataluna", "galicia"]),
        "galicia": Catalog(id="galicia", name="Galicia", scope="", protocol="z3950", host="x", regions=["galicia"]),
    }
    f = FederatedSearch(cats, timeout=2)
    calls = []

    def fake(cat, c, n, with_holdings):
        calls.append(cat.id)
        if cat.id == "aladi":
            return 1, [_book("aladi",
                             ("Biblioteca Central de Sabadell", "available"),
                             ("Biblioteca de Ripollet", "checked_out"),
                             ("Biblioteca de Barberà del Vallès", "available"),
                             ("Biblioteca Clarà (Barcelona)", "available"),
                             ("Biblioteca Desconocida", "unknown"),
                             ("Xarxa de la Diputació de Barcelona", "unknown"))]
        if cat.id == "ccbip":
            return 1, [_book("ccbip",
                             ("Biblioteca Pública de Montcada i Reixac", "available"),
                             ("Biblioteca de Ripollet", "available"))]
        return 1, [_book("galicia", ("Biblioteca de Lugo", "available"))]

    monkeypatch.setattr(f, "_z3950", fake)
    f.calls = calls
    return f


async def test_proximity_order_from_barbera(fed):
    gf = fed.geo.filter(near="Barbera del Valles")
    r = await fed.locate(SearchCriteria(isbn="9788408172178"), geo_filter=gf)
    with_dist = [u for u in r["locations"] if "distance_km" in u]
    assert [u["municipality"] for u in with_dist] == [
        "Barberà del Vallès", "Ripollet", "Ripollet", "Sabadell", "Montcada i Reixac", "Barcelona"]
    assert with_dist[0]["distance_km"] == 0.0
    d = [u["distance_km"] for u in with_dist]
    assert d == sorted(d) and 2 < d[1] < 4  # Ripollet is ~3.3 km away
    # at equal distance (Ripollet), available comes before checked_out
    assert [u["status"] for u in with_dist[1:3]] == ["available", "checked_out"]
    # unlocated libraries go last and are reported
    assert all("distance_km" not in u for u in r["locations"][len(with_dist):])
    assert set(r["unlocated_libraries"]) == {"Biblioteca Desconocida", "Xarxa de la Diputació de Barcelona"}
    assert "galicia" not in fed.calls  # municipality's region narrows the catalogs queried


async def test_radius_county_and_municipality_filters(fed):
    crit = SearchCriteria(isbn="9788408172178")
    r = await fed.locate(crit, geo_filter=fed.geo.filter(near="Barberà del Vallès", radius_km=5))
    assert {u["municipality"] for u in r["locations"]} == {"Barberà del Vallès", "Ripollet", "Sabadell"}
    assert r["holdings_outside_filter"] == 4  # Montcada, Barcelona, and the 2 unlocated
    assert "excluded" in r["notice"]

    r = await fed.locate(crit, geo_filter=fed.geo.filter(county="Vallès Occidental"))
    assert {u["municipality"] for u in r["locations"]} == {
        "Barberà del Vallès", "Ripollet", "Montcada i Reixac", "Sabadell"}

    r = await fed.locate(crit, geo_filter=fed.geo.filter(municipality="ripollet"))
    assert [u["status"] for u in r["locations"]].count("available") == 1 and len(r["locations"]) == 2

    r = await fed.locate(crit, geo_filter=fed.geo.filter(province="barcelona"), available_only=True)
    assert all(u["status"] == "available" for u in r["locations"])


async def test_cache_is_not_polluted_by_geo(fed):
    crit = SearchCriteria(isbn="9788408172178")
    await fed.search(crit, ids=["aladi"], geo_filter=fed.geo.filter(near="Ripollet"))
    r = await fed.search(crit, ids=["aladi"])  # same query, no geo
    holdings = r["results"][0]["books"][0]["holdings"]
    assert len(holdings) == 6 and all("municipality" not in h and "_m" not in h for h in holdings)
    assert fed.calls.count("aladi") == 1  # second call came from cache


async def test_search_without_geo_unchanged(fed):
    r = await fed.search(SearchCriteria(isbn="9788408172178"), ids=["ccbip"])
    assert "geo" not in r and len(r["results"][0]["books"][0]["holdings"]) == 2


# ---------- municipality updater ----------

CSV_GENCAT = """Codi INE,Nom del municipi,Nom comarca,Latitud,Longitud,UTM X,UTM Y
080193,Barcelona,Barcelonès,"41,3874","2,1686",430000,4580000
081018,"Hospitalet de Llobregat, l'",Barcelonès,41.3596,2.0997,425000,4580000
170015,Girona,Gironès,41.9794,2.8214,0,0
,No coordinates,X,,,,
"""


def test_updater_converts_csv(tmp_path):
    rows, cols = updater.convert(CSV_GENCAT)
    assert cols["lat"] == "Latitud" and cols["lon"] == "Longitud" and cols["name"] == "Nom del municipi"
    assert [f["name"] for f in rows] == ["Barcelona", "Hospitalet de Llobregat, l'", "Girona"]
    assert rows[0]["province"] == "Barcelona" and rows[2]["province"] == "Girona"
    assert rows[0]["lat"] == "41.38740"
    output = tmp_path / "m.csv"
    updater.write_csv(rows, output)
    from spain_libraries_mcp.geo import _read_municipalities
    ms = _read_municipalities(output)
    assert "L'Hospitalet de Llobregat" in {m.name for m in ms} and not any(m.approx for m in ms)


def test_updater_fails_without_required_columns():
    with pytest.raises(SystemExit):
        updater.convert("a,b\n1,2\n")


def test_geo_haversine_antipodes_and_boundary_coordinates(geo):
    # Antipodes must not raise ValueError from floating-point rounding
    assert 20000 < haversine_km(0.0, 0.0, 0.0, 180.0) < 20030
    # Integer coordinates and alternative separators
    o = geo.origin("41; 2")
    assert (o.lat, o.lon) == (41.0, 2.0)
    with pytest.raises(ValueError, match="out of range"):
        geo.origin("95.0,2.0")
    with pytest.raises(ValueError, match="out of range"):
        geo.origin("41.0,-185.0")
    with pytest.raises(ValueError, match="greater than 0"):
        geo.filter(near="Barcelona", radius_km=-1)
    with pytest.raises(ValueError, match="Empty municipality"):
        geo.municipality("   ")


def test_geo_load_custom_files_and_directory_priority(tmp_path, monkeypatch):
    m_csv = tmp_path / "m.csv"
    m_csv.write_text(
        "# comment\nname,province,county,region,lat,lon,approx\n"
        "Ripollet,Barcelona,Vallès Occidental,cataluna,41.4972,2.1590,0\n"
        "Sabadell,Barcelona,Vallès Occidental,cataluna,41.5463,2.1086,0\n"
        "BrokenRow,Barcelona,X,cataluna,not_a_float,2.0,0\n",
        encoding="utf-8",
    )
    d_csv = tmp_path / "d.csv"
    d_csv.write_text(
        "catalog,key,name,municipality\n"
        ",COD1,Global,Ripollet\n"
        "aladi,COD1,Specific,Sabadell\n"
        "aladi,BAD,Broken,NonExistentMunicipality\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SPAIN_LIBRARIES_MUNICIPALITIES", str(m_csv))
    monkeypatch.setenv("SPAIN_LIBRARIES_DIRECTORY", str(d_csv))
    g = Geo.load()
    assert len(g.municipalities) == 2
    # Catalog-specific entry takes precedence over global entry
    assert g.locate("aladi", {"library": "COD1"}) == (g.municipality("Sabadell"), "directory")
    assert g.locate("ccbip", {"library": "COD1"}) == (g.municipality("Ripollet"), "directory")
    # Invalid directory entry falls back to name heuristic
    assert g.locate("aladi", {"library": "BAD", "location": "Biblioteca de Ripollet"}) == (
        g.municipality("Ripollet"), "name"
    )


def test_updater_main_cli(tmp_path, monkeypatch):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.csv"
    inp.write_text(CSV_GENCAT, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["spain-libraries-update-municipalities", "--input", str(inp), "--output", str(out)])
    updater.main()
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Barcelona" in content and "Girona" in content
