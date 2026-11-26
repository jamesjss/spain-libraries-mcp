from spain_libraries_mcp import marc


def test_parse_marcxml_invalid_or_missing_record():
    assert marc.parse_marcxml("<unclosed", "test") is None
    assert marc.parse_marcxml("<root><other/></root>", "test") is None
    assert marc.parse_marcxml("<collection><record/></collection>", "test") is None


def test_parse_marcxml_full_fields_and_fallbacks():
    xml = """<collection xmlns="http://www.loc.gov/MARC21/slim">
      <record>
        <controlfield tag="001">  ID-42 / </controlfield>
        <controlfield tag="008">200101s1985    sp            000 1 cat d</controlfield>
        <datafield tag="020" ind1=" " ind2=" "><subfield code="a">978-84-000-0001-1 (hardcover)</subfield></datafield>
        <datafield tag="020" ind1=" " ind2=" "><subfield code="a">84-000-0001-X</subfield></datafield>
        <datafield tag="020" ind1=" " ind2=" "><subfield code="a">9788400000011</subfield></datafield>
        <datafield tag="110" ind1="2" ind2=" "><subfield code="a">Institut d'Estudis Catalans.</subfield></datafield>
        <datafield tag="245" ind1="0" ind2="0">
          <subfield code="a">Diccionari :</subfield>
          <subfield code="b">edició escolar /</subfield>
        </datafield>
        <datafield tag="250" ind1=" " ind2=" "><subfield code="a">3a ed.</subfield></datafield>
        <datafield tag="260" ind1=" " ind2=" "><subfield code="b">Editorial X,</subfield></datafield>
        <datafield tag="650" ind1=" " ind2=" "><subfield code="a">  /  </subfield></datafield>
        <datafield tag="650" ind1=" " ind2=" "><subfield code="a">Lingüística.</subfield></datafield>
        <datafield tag="651" ind1=" " ind2=" "><subfield code="a">Catalunya.</subfield></datafield>
      </record>
    </collection>"""
    book = marc.parse_marcxml(xml, "bne")
    assert book is not None
    assert book.id == "ID-42"
    assert book.title == "Diccionari : edició escolar"
    assert book.author == "Institut d'Estudis Catalans"
    assert book.edition == "3a ed"
    assert book.publisher == "Editorial X"
    assert book.year == "1985"  # fallback to 008 when 260$c is absent
    assert book.language == "cat"
    assert book.isbn == ["840000001X", "9788400000011"]
    assert book.subjects == ["Lingüística", "Catalunya"]  # skips empty "$a /"

    d = book.to_dict()
    assert "holdings" not in d and "link" not in d


def test_koha_all_statuses():
    xml = """<record>
      <datafield tag="245"><subfield code="a">Book</subfield></datafield>
      <datafield tag="952"><subfield code="b">BIB1</subfield><subfield code="c">Room</subfield><subfield code="o">CALL1</subfield></datafield>
      <datafield tag="952"><subfield code="a">BIB2</subfield><subfield code="q">2026-12-31</subfield></datafield>
      <datafield tag="952"><subfield code="b">BIB3</subfield><subfield code="1">1</subfield></datafield>
      <datafield tag="952"><subfield code="b">BIB4</subfield><subfield code="0">2</subfield></datafield>
      <datafield tag="952"><subfield code="b">BIB5</subfield><subfield code="7">1</subfield></datafield>
    </record>"""
    book = marc.parse_marcxml(xml, "galicia", "koha")
    assert [(h.library, h.status) for h in book.holdings] == [
        ("BIB1", "available"),
        ("BIB2", "checked_out"),
        ("BIB3", "lost"),
        ("BIB4", "lost"),
        ("BIB5", "not_for_loan"),
    ]


def test_alma_ava_edge_cases():
    xml = """<record>
      <datafield tag="245"><subfield code="a">Book</subfield></datafield>
      <datafield tag="AVA"><subfield code="b">CSIC</subfield><subfield code="e">unavailable</subfield><subfield code="f">2</subfield><subfield code="g">5</subfield></datafield>
      <datafield tag="AVA"><subfield code="b">CSIC</subfield><subfield code="e">check_holdings</subfield><subfield code="f">?</subfield></datafield>
    </record>"""
    book = marc.parse_marcxml(xml, "csic", "alma")
    h1, h2 = book.holdings
    assert (h1.status, h1.total, h1.available) == ("checked_out", 2, 0)  # clamped at 0
    assert (h2.status, h2.total, h2.available) == ("unknown", None, None)  # non-numeric f


def test_sierra_852_850_and_generic_holdings():
    xml = """<record>
      <datafield tag="245"><subfield code="a">Book</subfield></datafield>
      <datafield tag="907"><subfield code="i">b01</subfield><subfield code="i">b02</subfield></datafield>
      <datafield tag="945"><subfield code="l">barb</subfield><subfield code="a">N CER</subfield><subfield code="s">-</subfield></datafield>
      <datafield tag="945"><subfield code="l">ripo</subfield><subfield code="s">o</subfield></datafield>
      <datafield tag="945"><subfield code="l">saba</subfield></datafield>
      <datafield tag="852"><subfield code="b">BPLU</subfield><subfield code="h">82</subfield><subfield code="i">CER</subfield></datafield>
      <datafield tag="852"><subfield code="a">BNE</subfield><subfield code="b">Recoletos</subfield><subfield code="c">Room</subfield></datafield>
      <datafield tag="850"><subfield code="a">UCM</subfield><subfield code="a">UB</subfield></datafield>
      <datafield tag="949"><subfield code="m">BIBX</subfield><subfield code="d">CALLX</subfield></datafield>
    </record>"""
    book = marc.parse_marcxml(xml, "aladi", "sierra")
    summary = [(h.source, h.library, h.location, h.call_number, h.status) for h in book.holdings]
    assert summary == [
        ("907$i", "b01", None, None, "unknown"),
        ("907$i", "b02", None, None, "unknown"),
        ("945", "barb", None, "N CER", "available"),
        ("945", "ripo", None, None, "unavailable"),
        ("945", "saba", None, None, "unknown"),
        ("852", "BPLU", None, "82 CER", "unknown"),  # does not duplicate $b into location
        ("852", "BNE", "Room", None, "unknown"),
        ("850", "UCM", None, None, "unknown"),
        ("850", "UB", None, None, "unknown"),
        ("949", "BIBX", None, "CALLX", "unknown"),
    ]


def test_opac_holdings_various_formats():
    opac_xml = """<opacRecord>
      <holdings>
        <holding>
          <nucCode>BCN1</nucCode>
          <localLocation>Biblioteca Clarà</localLocation>
          <callNumber>N ZAF</callNumber>
          <shelvingData>Floor 1</shelvingData>
          <publicNote>Reading room only</publicNote>
          <circulations>
            <circulation><availableNow value="1"/></circulation>
            <circulation><availableNow value="0"/></circulation>
          </circulations>
        </holding>
        <holding>
          <localLocation>Biblioteca Ripollet</localLocation>
          <circulations>
            <circulation><availableNow>0</availableNow></circulation>
          </circulations>
        </holding>
        <holding>
          <localLocation>Biblioteca Sabadell</localLocation>
          <circulations>
            <circulation><availableNow>1</availableNow></circulation>
          </circulations>
        </holding>
        <holding>
          <localLocation>No Circulation Library</localLocation>
        </holding>
      </holdings>
    </opacRecord>"""
    hs = marc.opac_holdings(opac_xml)
    assert len(hs) == 4
    assert (hs[0].library, hs[0].status, hs[0].available, hs[0].total) == ("BCN1", "available", 1, 2)
    assert hs[0].details == {"shelving": "Floor 1", "notes": "Reading room only"}
    assert (hs[1].library, hs[1].status, hs[1].available, hs[1].total) == ("Biblioteca Ripollet", "checked_out", 0, 1)
    assert (hs[2].library, hs[2].status, hs[2].available, hs[2].total) == ("Biblioteca Sabadell", "available", 1, 1)
    assert (hs[3].library, hs[3].status, hs[3].available, hs[3].total) == ("No Circulation Library", "unknown", None, None)
    assert marc.opac_holdings("<broken") == []
