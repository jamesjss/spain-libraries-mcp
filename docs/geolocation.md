# Proximity Search

> **Language:** English | [Español](es/geolocalizacion.md)

Lets you ask "where can I find this book near Barcelona?" and get holdings sorted from
closest to farthest.

## Parameters

Available in `search_books` and `locate_holdings`:

| Parameter | Effect |
|---|---|
| `near` | Municipality (with or without accents, supports prefixes like `barbera`) or coordinates `"41.39,2.17"`. Sorts by distance and adds `distance_km`. |
| `radius_km` | With `near`: excludes holdings farther than this radius. |
| `municipality` | Only holdings in that municipality. |
| `province` | Only holdings in that province. |
| `county` | Only holdings in that county / comarca (e.g. `Vallès Occidental`). |
| `available_only` | `locate_holdings` only: omits checked-out holdings and unknown status. |

Criteria can be combined. If neither `catalogs` nor `region` is provided, the server queries the
catalogs for the municipality's region plus national catalogs (BNE, REBIUN, CSIC).

## Example

`locate_holdings(isbn="9788408172178", near="Barcelona")` (simulated data):

```
  0.0 km  Barcelona              available    Biblioteca Clarà (Barcelona)
  7.2 km  Badalona               checked_out  Biblioteca Can Casacuberta - Badalona
 12.1 km  Ripollet               available    Biblioteca Ripollet
 18.4 km  Sabadell               available    Biblioteca Central de Sabadell
```

At equal distance, an available copy appears before a checked-out one. Holdings that cannot be
located appear at the end, without a distance.

## How a Holding Is Located

A catalog only reports which library holds the copy. Its municipality is resolved in two steps:

1. **Directory** (`data/libraries.csv`, optional): `catalog,key,name,municipality`. `key` is the
   exact code or name returned by the catalog. This is the most reliable method and always wins.
   Shown in responses as `location_source: "directory"`.
2. **Name heuristic**: if the library text contains a known municipality name
   (`Biblioteca Central de Sabadell`), that municipality is used. Shown as
   `location_source: "name"`. Noise phrases like "Diputació de Barcelona" or "Xarxa de Biblioteques"
   are ignored.

Unlocated libraries are **never silently dropped**: the response includes `unlocated_libraries`
(with copy counts) and a `notice`. When `radius_km`, `municipality`, `province`, or `county` is
active, unlocated libraries are excluded because filter compliance cannot be verified; with `near`
alone, they are placed at the end.

To improve coverage, add unlocated libraries from the notice to `data/libraries.csv`:

```csv
catalog,key,name,municipality
aladi,BSAB,Biblioteca Central de Sabadell,Sabadell
```

## Municipality Data

- **Bundled:** `src/spain_libraries_mcp/data/municipalities.csv` ships with 21 Barcelona-area
  municipalities with **approximate** coordinates (town center, ~1 km precision; `approx=1`). Good
  for getting started, not official data.
- **Official data for all of Catalonia:**
  [Caps de municipi de Catalunya georeferenciats](https://analisi.transparenciacatalunya.cat/Sector-P-blic/Caps-de-municipi-de-Catalunya-georeferenciats/wpyq-we8x)
  (Generalitat / ICGC). Download with:

  ```bash
  spain-libraries-update-municipalities                              # downloads and overwrites bundled file
  spain-libraries-update-municipalities --output ~/municipalities.csv
  export SPAIN_LIBRARIES_MUNICIPALITIES=~/municipalities.csv         # or point to your custom file
  ```

  Portal column names are detected by keywords, printed to stderr, and validated with a clear error
  if name or coordinates cannot be found.
- **Other regions:** the CSV format is `name,province,county,region,lat,lon,approx`. Add rows with
  lowercase ASCII `region` values (`madrid`, `galicia`, etc.) and they will work identically.

## Known Limitations

- Distance is straight-line (haversine) between town centers, not road or transit distance.
  Two libraries in the same municipality have the same distance.
- Each municipality uses a single coordinate point (Barcelona city is not split by neighborhoods).
- Without a directory entry, libraries whose names do not include the municipality remain unlocated.
