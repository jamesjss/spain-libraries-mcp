"""MCP server for searching books and holdings in Spanish libraries."""

from __future__ import annotations

import argparse
import os

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__
from .queries import SearchCriteria
from .service import FederatedSearch

INSTRUCTIONS = """\
Search books across Spanish library catalogs (CCBIP: over 3,800 public libraries across all regions;
BNE; REBIUN university libraries; CSIC; Aladí in Barcelona province; Galicia and Basque Country
networks). Use `search_books` to find works, `locate_holdings` to check which libraries hold copies
and whether they are available, and `list_catalogs` to inspect coverage. If the user mentions where
they live or want to pick up a book, pass `near` (municipality or coordinates) to sort holdings by
distance and `radius_km` to limit results. If a catalog returns no holdings, offer the
`opac_search_url` link. Availability is only reliable when status is 'available' or 'checked_out';
'unknown' means the library holds the book but the catalog does not report loan status.
"""

mcp = MCPServer("spain-libraries", instructions=INSTRUCTIONS, version=__version__)
_fed: FederatedSearch | None = None


def fed() -> FederatedSearch:
    global _fed
    if _fed is None:
        _fed = FederatedSearch.from_env()
        _fed.timeout = int(os.environ.get("SPAIN_LIBRARIES_TIMEOUT", "20"))
    return _fed


def _geo_filter(near, radius_km, municipality, province, county):
    try:
        return fed().geo.filter(near=near, radius_km=radius_km, municipality=municipality,
                                province=province, county=county)
    except ValueError as e:  # ToolError keeps the message visible to the model
        raise ToolError(str(e)) from e


@mcp.tool()
def list_catalogs(region: str | None = None, include_inactive: bool = False) -> list[dict]:
    """List available library catalogs, their coverage, and connection metadata.

    Args:
        region: autonomous community (e.g. "catalonia", "galicia", "madrid") to filter by.
        include_inactive: include catalogs disabled by default (e.g. bibliographic heritage).
    """
    return [c.to_public() for c in fed().select(region=region, include_inactive=include_inactive)]


@mcp.tool()
async def search_books(
    title: str | None = None,
    author: str | None = None,
    isbn: str | None = None,
    subject: str | None = None,
    text: str | None = None,
    catalogs: list[str] | None = None,
    region: str | None = None,
    max_per_catalog: int = 5,
    near: str | None = None,
    radius_km: float | None = None,
    municipality: str | None = None,
    province: str | None = None,
    county: str | None = None,
) -> dict:
    """Search for books in parallel across Spanish library catalogs.

    Combines criteria with AND. Returns, per catalog, the total hit count and the first
    records (title, author, publisher, year, ISBN, and holdings if present).
    With `near`, holdings for each book are sorted by proximity.

    Args:
        title: words from the title.
        author: author's last or full name.
        isbn: ISBN-10 or ISBN-13 (with or without hyphens). Most accurate search.
        subject: topic or subject heading.
        text: free-text search across any field.
        catalogs: specific catalog IDs (see list_catalogs). If omitted, all active catalogs.
        region: limit to catalogs covering that autonomous community.
        max_per_catalog: records to fetch per catalog (1-20).
        near: municipality (e.g. "Barcelona", with or without accents) or coordinates "41.39,2.17".
            Sorts holdings closest first and adds `distance_km`.
        radius_km: with `near`, exclude holdings farther than this distance.
        municipality: only holdings in that municipality.
        province: only holdings in that province (e.g. "Barcelona").
        county: only holdings in that county / comarca (e.g. "Vallès Occidental").
    """
    gf = _geo_filter(near, radius_km, municipality, province, county)
    try:
        return await fed().search(SearchCriteria(title, author, isbn, subject, text), ids=catalogs, region=region,
                                  max_per_catalog=max_per_catalog, geo_filter=gf)
    except ValueError as e:
        raise ToolError(str(e)) from e


@mcp.tool()
async def locate_holdings(
    isbn: str | None = None,
    title: str | None = None,
    author: str | None = None,
    catalogs: list[str] | None = None,
    region: str | None = None,
    max_per_catalog: int = 5,
    near: str | None = None,
    radius_km: float | None = None,
    municipality: str | None = None,
    province: str | None = None,
    county: str | None = None,
    available_only: bool = False,
) -> dict:
    """Find which libraries hold copies of a book and, if reported, whether they are available.

    Requests Z39.50 OPAC syntax (with circulation data) and falls back to MARC holdings fields
    when unsupported. With `near`, returns a single list sorted by distance (closest first;
    available copies before checked-out copies at equal distance). Libraries that cannot be
    matched to a municipality are reported separately instead of being silently dropped.

    Args:
        isbn: book ISBN (recommended).
        title: book title, if ISBN is unavailable.
        author: author name, to narrow results.
        catalogs: specific catalog IDs; if omitted, all active catalogs (or those for the municipality's region).
        region: autonomous community, e.g. "catalonia" or "andalusia".
        max_per_catalog: editions/records to inspect per catalog.
        near: municipality (e.g. "Barcelona", with or without accents) or coordinates "41.39,2.17".
            Sorts by distance and adds `distance_km`.
        radius_km: with `near`, exclude holdings farther than this distance.
        municipality: only holdings in that municipality.
        province: only holdings in that province (e.g. "Barcelona").
        county: only holdings in that county / comarca (e.g. "Vallès Occidental").
        available_only: omit checked-out holdings and holdings with unknown status.
    """
    gf = _geo_filter(near, radius_km, municipality, province, county)
    try:
        return await fed().locate(SearchCriteria(title, author, isbn), ids=catalogs, region=region,
                                  max_per_catalog=max_per_catalog, geo_filter=gf, available_only=available_only)
    except ValueError as e:
        raise ToolError(str(e)) from e


@mcp.tool()
async def check_catalogs() -> list[dict]:
    """Check connectivity to each catalog with a test query and return latency or error."""
    return await fed().check()


def main() -> None:
    p = argparse.ArgumentParser(description="MCP server for Spanish libraries")
    p.add_argument("--transport", choices=["stdio", "streamable-http"], default=os.environ.get("MCP_TRANSPORT", "stdio"))
    p.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    a = p.parse_args()
    if a.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host=a.host, port=a.port)


if __name__ == "__main__":
    main()
