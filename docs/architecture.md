# Architecture

> **Language:** English | [Español](es/arquitectura.md)

```
MCP Client (Claude) ──► server.py (MCPServer, 4 tools)
                             │
                             ▼
                  service.FederatedSearch ── 5 min cache, max 2 concurrent queries per catalog
                        │            │
          asyncio.to_thread       async httpx
                │                    │
            zoom.py (Z39.50)      sru.py (SRU 1.2 / CQL)
      ctypes → libyaz (ZOOM API)     │
                │                    │
                └──── MARCXML ───────┘
                         │
                     marc.py ── Book + Holdings (koha / alma / sierra / absysnet / OPAC profiles)
```

## Modules

- `catalogs.py`: catalog registry (connection settings, coverage, source, and verification status). Extensible via JSON.
- `queries.py`: translates `SearchCriteria` (title, author, ISBN, subject, text) to PQF (Bib-1 attributes) and CQL.
- `zoom.py`: `ctypes` wrapper around 13 functions of the YAZ ZOOM API. Fetches records as `raw`, `xml` (YAZ converts ISO-8859-1/MARC-8 → UTF-8), and `opac` when using OPAC syntax.
- `sru.py`: SRU 1.2 client; detects SRU diagnostic errors.
- `marc.py`: extracts bibliographic metadata and normalizes holdings by source ILS profile.
- `geo.py`: municipalities, holding placement (directory or name heuristic), and distance sorting (haversine). See [geolocation.md](geolocation.md).
- `updater.py`: generates `data/municipalities.csv` from official Generalitat data.
- `service.py`: parallel federated search. A down or slow catalog returns its `error` without affecting the others.
- `server.py`: MCP tools and CLI entrypoint (`stdio` or `streamable-http`).

## Design Decisions

- **YAZ via `ctypes` instead of a pure-Python Z39.50 client.** Z39.50 uses ASN.1/BER and real-world servers (AbsysNet, Sierra) have many quirks. YAZ has 25+ years of production use in Koha, VuFind, and others, and there are no actively maintained Python bindings on PyPI.
- **No OPAC web scraping.** Scraping is brittle and disallowed by some catalogs' `robots.txt` (e.g. Aladí). An OPAC search URL is returned instead.
- **mcp 2.x** (`MCPServer`).

## Tests

- `tests/test_geo.py`: proximity search (sorting, radius, county, cache isolation, and municipality updater) without network access.
- `tests/test_marc.py`, `tests/test_queries.py`, `tests/test_sru_and_catalogs.py`, `tests/test_service_and_mcp.py`: unit and mock tests covering MARC/OPAC parsing, PQF/CQL generation, SRU, catalog loading, retry logic, caching, and MCP tool errors.
- `tests/test_libraries.py`: spawns `yaz-ztest` (a real Z39.50 server from YAZ) on a free port and tests the ZOOM client, OPAC syntax with availability, catalog error isolation, and MCP tools end to end.
