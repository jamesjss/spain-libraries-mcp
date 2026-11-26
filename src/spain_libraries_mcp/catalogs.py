"""Registry of Spanish library catalogs accessible via standard protocols.

Each entry documents where the connection details come from (`source`). Entries marked
with `verified=False` come from older documentation and should be checked with the
`check_catalogs` tool before relying on them.

You can add or override catalogs using a custom JSON file specified in the
`SPAIN_LIBRARIES_CATALOGS` environment variable (a list of objects with the same fields).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Literal
from urllib.parse import quote_plus

Protocol = Literal["z3950", "sru"]


@dataclass
class Catalog:
    id: str
    name: str
    scope: str  # what it covers, in plain language
    protocol: Protocol
    host: str = ""
    port: int = 210
    database: str = ""
    charset: str = "utf-8"
    syntax: str = "usmarc"  # "opac" also requests holdings/circulation data
    user: str | None = None
    password: str | None = None
    sru_url: str = ""  # for sru protocol
    sru_indices: dict[str, str] = field(default_factory=dict)
    timeout: int | None = None  # seconds; None = federated search default
    pqf_extra: str = ""  # extra PQF attributes added to each term (e.g. "@attr 3=3")
    holdings_profile: str = "generic"  # absysnet | koha | sierra | alma | generic
    opac_search: str = ""  # URL template with {q}
    regions: list[str] = field(default_factory=list)
    active: bool = True
    verified: bool = True
    source: str = ""

    def opac_url(self, q: str) -> str | None:
        return self.opac_search.format(q=quote_plus(q)) if self.opac_search else None

    def to_public(self) -> dict:
        d = asdict(self)
        d.pop("password", None)
        d.pop("user", None)
        return d


ALL_REGIONS = [
    "andalucia", "aragon", "asturias", "baleares", "canarias", "cantabria",
    "castilla-la-mancha", "castilla-y-leon", "cataluna", "ceuta", "extremadura",
    "galicia", "la-rioja", "madrid", "melilla", "murcia", "navarra",
    "pais-vasco", "valencia",
]

DEFAULT_CATALOGS: list[Catalog] = [
    Catalog(
        id="ccbip",
        name="Union Catalog of Spanish Public Libraries (CCBIP)",
        scope=(
            "Over 3,800 public libraries: the 53 State Public Libraries (BPE) and 16 regional "
            "networks (Andalusia, Aragon, Asturias, Canary Islands, Cantabria, Castile and Leon, "
            "Castilla-La Mancha, Catalonia-Argus, Madrid, Navarre, Valencia, Extremadura, "
            "Galicia, La Rioja, Basque Country, Murcia). Balearic Islands, Ceuta, and Melilla "
            "are included via their BPEs only."
        ),
        protocol="z3950",
        host="catalogos.mecd.es",
        port=212,
        database="ABNET_DB",
        charset="iso-8859-1",
        timeout=45,  # slow server; if it still times out, try another host via SPAIN_LIBRARIES_CATALOGS
        holdings_profile="absysnet",
        opac_search="http://catalogos.mecd.es/CCBIP/ccbipopac/",
        regions=ALL_REGIONS,
        source="https://www.cultura.gob.es/dam/jcr:3dece3fd-d232-440a-9f17-0427b75fba21/folleto-ccbip-2021.pdf",
    ),
    Catalog(
        id="bne",
        name="National Library of Spain (BNE)",
        scope="BNE collections (legal deposit: virtually everything published in Spain).",
        protocol="sru",
        sru_url="https://catalogo.bne.es/view/sru/34BNE_INST",
        sru_indices={
            "title": "alma.title",
            "author": "alma.creator",
            "isbn": "alma.isbn",
            "subject": "alma.subjects",
            "text": "alma.all_for_ui",
        },
        holdings_profile="alma",
        opac_search="https://catalogo.bne.es/discovery/search?query=any,contains,{q}&vid=34BNE_INST:CATALOGO",
        regions=ALL_REGIONS,  # national catalog: included in any regional search
        source="https://bne.es/en/profiles/librarians/record-supply/descarga-sru",
    ),
    Catalog(
        id="rebiun",
        name="REBIUN – Union Catalog of Spanish University Libraries",
        scope="76 university and CSIC libraries across Spain.",
        protocol="z3950",
        host="rebiun.crue.org",
        port=210,
        database="ABSYSREBIUN",
        holdings_profile="absysnet",
        regions=ALL_REGIONS,
        source="https://www.rebiun.org/sites/default/files/2017-11/Provisional_Manual%20de%20procedimiento%20%20REBIUN_corregido_oct17.pdf",
    ),
    Catalog(
        id="csic",
        name="CSIC Library and Archive Network",
        scope="Libraries of the Spanish National Research Council (CSIC) institutes.",
        protocol="z3950",
        host="eu00.alma.exlibrisgroup.com",
        port=1921,
        database="34CSIC_INST",
        holdings_profile="alma",
        regions=ALL_REGIONS,
        source="https://sitios.csic.es/web/red-de-bibliotecas/servidor-z3950",
    ),
    Catalog(
        id="aladi",
        name="Aladí – Municipal Library Network (Diputació de Barcelona)",
        scope=(
            "Municipal libraries in the province of Barcelona (including Barcelona city). "
            "Not part of CCBIP, so it is queried separately."
        ),
        protocol="z3950",
        host="aladi.diba.cat",
        port=210,
        database="INNOPAC",
        pqf_extra="@attr 3=3",  # position "any": Sierra rejects 4=6 with position "first"
        holdings_profile="sierra",
        opac_search="https://aladi.diba.cat/search*cat/?searchtype=X&searcharg={q}",
        regions=["cataluna"],
        verified=False,
        source="https://github.com/abematt/aladi-catalogue (enrich.py)",
    ),
    Catalog(
        id="galicia",
        name="Galicia Public Library Network",
        scope="Union catalog of the Galician public library network, with item availability.",
        protocol="z3950",
        host="z3950-rbgalicia.xunta.gal",
        port=9998,
        database="biblios",
        holdings_profile="koha",
        regions=["galicia"],
        source="https://rbgalicia.xunta.gal/es/catalogo-de-la-red-de-bibliotecas-publicas-de-galicia",
    ),
    Catalog(
        id="euskadi",
        name="Basque Public Reading Network (Euskadi)",
        scope="Municipal libraries of the Basque Country.",
        protocol="z3950",
        host="z39-katalogoak.euskadi.eus",
        port=2210,
        database="ABNET_DB_CATA",
        user="z3950",
        password="absysNET",  # public credentials published by the Basque Government
        holdings_profile="absysnet",
        regions=["pais-vasco"],
        source="https://www.euskadi.eus/catalogo-en-linea-opac/web01-a2libzer/es/",
    ),
    Catalog(
        id="ccpb",
        name="Union Catalog of Spanish Bibliographic Heritage (CCPB)",
        scope="Rare books and bibliographic heritage (manuscripts, early printed books) in Spanish libraries.",
        protocol="z3950",
        host="ccpb.mcu.es",
        port=210,
        database="absysccpb",
        holdings_profile="absysnet",
        regions=ALL_REGIONS,
        active=False,
        verified=False,
        source="Correo Bibliotecario (Ministry of Culture), older reference",
    ),
]


def load_catalogs() -> dict[str, Catalog]:
    cats = {c.id: c for c in DEFAULT_CATALOGS}
    path = os.environ.get("SPAIN_LIBRARIES_CATALOGS")
    if path:
        with open(path, encoding="utf-8") as f:
            for d in json.load(f):
                base = asdict(cats[d["id"]]) if d["id"] in cats else {}
                base.update(d)
                cats[d["id"]] = Catalog(**base)
    return cats
