# spain-libraries-mcp

> **Language:** English | [Español](README.es.md)

Python **MCP** (Model Context Protocol) server for searching books in Spanish libraries, finding
**which libraries hold copies**, and—when reported by the catalog—checking **whether they are available**.

No web scraping: it uses the standard library protocols published by the networks themselves for
machine access, **Z39.50** and **SRU**.

## Coverage

| ID | Catalog | Coverage | Protocol |
|---|---|---|---|
| `ccbip` | Union Catalog of Spanish Public Libraries (CCBIP) | 3,800+ public libraries: 53 State Public Libraries (BPE) and 16 regional networks | Z39.50 |
| `bne` | National Library of Spain (BNE) | Legal deposit | SRU |
| `rebiun` | REBIUN | University libraries and CSIC | Z39.50 |
| `csic` | CSIC Library Network | CSIC research institutes | Z39.50 |
| `aladi` | Aladí (Diputació de Barcelona) | Municipal libraries in Barcelona province (not in CCBIP) | Z39.50 |
| `galicia` | Galicia Public Library Network | Galician public network with item availability | Z39.50 |
| `euskadi` | Basque Public Reading Network | Basque municipal libraries | Z39.50 |
| `ccpb` | Spanish Bibliographic Heritage (inactive) | Rare books and heritage collections | Z39.50 |

Details, sources, and limitations in [docs/catalogs.md](docs/catalogs.md).

## MCP Tools

- `search_books(title, author, isbn, subject, text, catalogs, region, max_per_catalog, near, radius_km, municipality, province, county)`: searches all active catalogs in parallel.
- `locate_holdings(isbn | title, author, catalogs, region, near, radius_km, municipality, province, county, available_only)`: lists libraries holding copies and their status (`available`, `checked_out`, `not_for_loan`, `unavailable`, `lost`, `unknown`).
- `list_catalogs(region, include_inactive)`: shows catalog coverage and connection metadata.
- `check_catalogs()`: probes each catalog server and reports latency or errors.

### Proximity Search

`near="Barcelona"` sorts holdings from closest to farthest (adding `distance_km`),
while `radius_km`, `municipality`, `province`, or `county` filter results. How libraries are
located and what data is used: [docs/geolocation.md](docs/geolocation.md).

## Installation

Requires the native **YAZ** library (Index Data Z39.50 client):

```bash
# Debian/Ubuntu
sudo apt install libyaz5
# macOS
brew install yaz
```

Then install the package:

```bash
pip install .            # or: uv pip install .
spain-libraries-mcp      # stdio (for Claude Desktop / Claude Code)
spain-libraries-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

### Docker (recommended for homelabs)

```bash
docker compose up -d --build
# MCP endpoint: http://<host>:8000/mcp
```

The image already includes `libyaz5`. For Portainer, deploy `docker-compose.yml` as a stack.

### Claude Desktop / Claude Code

See `examples/claude_desktop_config.json`. In Claude Code:

```bash
claude mcp add spain-libraries -- spain-libraries-mcp
# or via HTTP
claude mcp add --transport http spain-libraries http://<host>:8000/mcp
```

## Configuration

| Environment Variable | Default | Purpose |
|---|---|---|
| `SPAIN_LIBRARIES_TIMEOUT` | `20` | Timeout in seconds per catalog |
| `SPAIN_LIBRARIES_CATALOGS` | — | JSON file to add, override, or enable catalogs (see `examples/extra-catalogs.json`) |
| `YAZ_LIB` | auto-detect | Path to `libyaz` if not found automatically |
| `SPAIN_LIBRARIES_MUNICIPALITIES` | bundled file | Municipalities CSV with coordinates (see `spain-libraries-update-municipalities`) |
| `SPAIN_LIBRARIES_DIRECTORY` | bundled file | CSV mapping library codes/names to municipalities |
| `MCP_TRANSPORT` / `MCP_HOST` / `MCP_PORT` | `stdio` / `127.0.0.1` / `8000` | Transport settings |

## First Step After Installing

Run the `check_catalogs` tool. Connection details come from each network's public documentation,
and a few (`aladi`, `ccpb`) are older or unofficial. If any catalog fails, override it via
`SPAIN_LIBRARIES_CATALOGS`.

## Tests

```bash
sudo apt install yaz        # includes yaz-ztest, a local Z39.50 test server
pip install -e ".[dev]" && pytest
```

## Responsible Use

These are public servers with limited resources: the server caps concurrency to 2 simultaneous
queries per catalog, caches results for 5 minutes, and avoids bulk harvesting. OPAC web pages are
never scraped (Aladí, for instance, disallows it in `robots.txt`); instead, a search URL is
returned so users can open it manually.
