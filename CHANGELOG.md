# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Renamed project, Python package (`spain_libraries_mcp`), CLI scripts (`spain-libraries-mcp`, `spain-libraries-update-municipalities`), MCP tools (`list_catalogs`, `search_books`, `locate_holdings`, `check_catalogs`), environment variables (`SPAIN_LIBRARIES_*`), classes, and code to English.
- Added bilingual documentation in English (default) and Spanish (`README.es.md`, `docs/es/`).
- Expanded unit and integration test suite covering MARC parsing, PQF/CQL queries, SRU, catalogs, geolocation, federated search, and MCP tool error handling.

## [0.2.1] - 2026-11-23

### Fixed
- Aladí (Sierra) rejected title searches (`Cannot Combine Wordlist Attribute with Position First in Field`, code 123): added position attribute `3=3` via the catalog's `pqf_extra` field.
- When a Z39.50 server returns an attribute error (codes 113–123), retries with simpler queries: `1=x 3=3 4=6` → `1=x 4=6` → `1=x`.
- CCBIP: per-catalog timeout (`timeout`, 45 s) because the server responds slowly or times out at 20 s.
- REBIUN marked as verified (responds properly).

## [0.2.0] - 2026-11-23

### Added
- Proximity search in book search and holdings lookup: `near` (municipality or coordinates), `radius_km`, `municipality`, `province`, `county`. Holdings are sorted by `distance_km`; at equal distance, available copies come first.
- `available_only` option for holdings lookup.
- `geo` module: locates each holding via directory (`data/libraries.csv`) or by matching a known municipality name in the library text. Unlocated libraries are reported in `unlocated_libraries`.
- `data/municipalities.csv` with 21 municipalities in the Barcelona area (approximate coordinates).
- CLI command `spain-libraries-update-municipalities` to generate the official list of Catalan municipalities (Generalitat / ICGC).
- Environment variables `SPAIN_LIBRARIES_MUNICIPALITIES` and `SPAIN_LIBRARIES_DIRECTORY`.
- Geolocation documentation and tests.

### Changed
- When `near` or `municipality` is provided without `region` or `catalogs`, queries the catalogs for that municipality's region plus national catalogs.
- BNE is treated as a national catalog in regional filtering.
- Geographic validation errors are surfaced to the model via `ToolError`.

### Pending
- Verify the municipality updater against the live Generalitat download (development environment had no internet access).
- Populate `data/libraries.csv` with real Aladí branch codes once the server is queried live.

## [0.1.0] - 2026-11-22

### Added
- Initial MCP server with catalog listing, book search, holdings lookup, and catalog connectivity checks.
- Z39.50 client over `libyaz` (ZOOM API via `ctypes`), with character set conversion and OPAC syntax support for availability.
- SRU 1.2 client for the National Library of Spain (BNE).
- Catalogs: CCBIP, BNE, REBIUN, CSIC, Aladí, Galicia, Euskadi, and CCPB (inactive by default).
- Holdings normalization for Koha (952), Alma (AVA), Sierra (907/945), AbsysNet (850/852/949/999), and OPAC records.
- Parallel federated search with 5-minute cache, max 2 concurrent queries per catalog, and error isolation.
- Extra catalogs configurable via JSON (`SPAIN_LIBRARIES_CATALOGS`).
- Dockerfile, `docker-compose.yml` (streamable-http transport), and Claude Desktop config example.
- Tests with `yaz-ztest` and sample MARC/SRU records.
