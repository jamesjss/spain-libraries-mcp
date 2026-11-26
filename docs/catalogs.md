# Catalogs and Access Protocols

> **Language:** English | [Español](es/catalogos.md)

## Why There Is No Single Catalog for Spain

Spain does not have a single unified database of all library holdings. Instead, there are union
catalogs aggregating networks, and each network runs its own integrated library system (AbsysNet,
Koha, Sierra, Alma, etc.). The standard machine-readable way to query them is **Z39.50** (binary
protocol over TCP) and, in some cases, **SRU** (its HTTP equivalent).

Project strategy:

1. **CCBIP** as the backbone: aggregates 16 regional networks and the 53 State Public Libraries (BPE).
2. **Catalogs not in CCBIP or offering richer item data** are queried separately:
   Aladí (Barcelona province), Galicia (per-item availability), Euskadi, BNE, REBIUN, and CSIC.

## Connection Details

| ID | Host | Port | Database | Charset | Source | Verified |
|---|---|---|---|---|---|---|
| ccbip | catalogos.mecd.es | 212 | ABNET_DB | ISO-8859-1 | [CCBIP Brochure 2021](https://www.cultura.gob.es/dam/jcr:3dece3fd-d232-440a-9f17-0427b75fba21/folleto-ccbip-2021.pdf), [España es Cultura](https://www.españaescultura.es/datos-abiertos/z39-50.html) | Yes (official docs) |
| bne | https://catalogo.bne.es/view/sru/34BNE_INST | – | SRU 1.2, CQL `alma.*` | UTF-8 | [BNE – SRU Download](https://bne.es/en/profiles/librarians/record-supply/descarga-sru) | Yes |
| bne (alt.) | z3950.bne.es | 210 | 34BNE_INST | UTF-8 | [BNE – Z39.50 Download](https://www.bne.es/es/perfiles/bibliotecarios/suministro-registros/descarga-z3950) | Yes |
| rebiun | rebiun.crue.org | 210 | ABSYSREBIUN | – | [REBIUN Manual 2017](https://www.rebiun.org/sites/default/files/2017-11/Provisional_Manual%20de%20procedimiento%20%20REBIUN_corregido_oct17.pdf) | Yes |
| csic | eu00.alma.exlibrisgroup.com | 1921 | 34CSIC_INST | UTF-8 | [CSIC](https://sitios.csic.es/web/red-de-bibliotecas/servidor-z3950) | Yes |
| aladi | aladi.diba.cat | 210 | INNOPAC | – | [abematt/aladi-catalogue](https://github.com/abematt/aladi-catalogue) | Unofficial |
| galicia | z3950-rbgalicia.xunta.gal | 9998 | biblios | UTF-8 | [RBGalicia](https://rbgalicia.xunta.gal/es/catalogo-de-la-red-de-bibliotecas-publicas-de-galicia) | Yes |
| euskadi | z39-katalogoak.euskadi.eus | 2210 | ABNET_DB_CATA (user `z3950`) | – | [Euskadi.eus](https://www.euskadi.eus/catalogo-en-linea-opac/web01-a2libzer/es/) | Yes |
| ccpb | ccpb.mcu.es | 210 | absysccpb | – | Correo Bibliotecario (older) | No, inactive |

Note: the REBECA page references `catalogos.cultura.gob.es`, so `mecd.es` may be migrating to
`cultura.gob.es`. If `ccbip` fails, try overriding its host.

## CCBIP Coverage by Region

According to the official brochure: Andalusia, Aragon, Asturias, Canary Islands, Cantabria,
Castile and Leon, Castilla-La Mancha, Catalonia (**Argus** only: Girona, Lleida, Tarragona),
Madrid, Navarre, Valencia, Extremadura, Galicia, La Rioja, Basque Country, and Murcia.
**Balearic Islands, Ceuta, and Melilla** contribute only their State Public Libraries.
**Barcelona province (Aladí)** is not included, which is why it has its own adapter.

## Availability (Checked Out / On Shelf)

Availability is the hardest part and depends on each server:

- **Z39.50 OPAC syntax**: when supported, returns `<holdings>` with `availableNow`. The MCP server
  requests it first in `locate_holdings` and falls back to USMARC if unsupported.
- **Koha (Galicia)**: field 952 includes library, call number, and due date (`$q`).
- **Alma (BNE, CSIC)**: field AVA includes library, total copies, and unavailable count.
- **Sierra (Aladí)**: 907 `$i` lists holding libraries without loan status.
- **AbsysNet (CCBIP, REBIUN, Euskadi)**: varies by installation. Raw 850/852/949/999 fields are
  returned when present; otherwise an OPAC search URL is provided.

When `status` is `unknown`, the library **does** hold the book, but the catalog does not report
whether it is currently checked out.

## Adding More Catalogs

Many universities and networks publish their Z39.50 parameters (search `"parámetros Z39.50"` +
institution name). You can add them without editing code via a JSON file pointed to by
`SPAIN_LIBRARIES_CATALOGS`; see `examples/extra-catalogs.json`. Key fields: `host`, `port`,
`database`, `charset` (`utf-8`, `iso-8859-1`, `marc8`), and `holdings_profile` (`koha`, `alma`,
`sierra`, `absysnet`).

BNE, REBIUN, and CSIC count as national catalogs: they are included in any `region` or `near` query.

## Compatibility Notes (0.2.1)

- **Aladí (Sierra/INNOPAC):** requires an explicit position attribute when using word-list structure. The catalog sets `pqf_extra="@attr 3=3"`.
- **Attribute retries:** on Z39.50 errors 113–123, queries are retried with fewer attributes (see `queries.to_pqf`, `variant` parameter).
- **CCBIP:** `catalogos.mecd.es:212` is slow or unreachable from some networks. It has its own 45 s timeout. If issues persist, override its host or `timeout` via `SPAIN_LIBRARIES_CATALOGS` (JSON).
- **REBIUN:** verified (`rebiun.crue.org:210`, `ABSYSREBIUN`).
