# Búsqueda por cercanía

> **Idioma:** [English](../geolocation.md) | Español

Permite preguntar "¿dónde hay este libro cerca de Barcelona?" y recibir los ejemplares
ordenados del más cercano al más lejano.

## Parámetros

Disponibles en `search_books` y `locate_holdings`:

| Parámetro | Efecto |
|---|---|
| `near` | Municipio (con o sin acentos, admite el principio del nombre: `barbera`) o coordenadas `"41.39,2.17"`. Ordena por distancia y añade `distance_km`. |
| `radius_km` | Con `near`: descarta lo que esté más lejos. |
| `municipality` | Solo ejemplares de ese municipio. |
| `province` | Solo ejemplares de esa provincia. |
| `county` | Solo ejemplares de esa comarca (`Vallès Occidental`). |
| `available_only` | Solo `locate_holdings`: omite prestados y estado desconocido. |

Los criterios se combinan. Si no se indica `catalogs` ni `region`, se consultan los catálogos de la
comunidad del municipio y los nacionales (BNE, REBIUN, CSIC).

## Ejemplo

`locate_holdings(isbn="9788408172178", near="Barcelona")` (datos simulados):

```
  0.0 km  Barcelona              available    Biblioteca Clarà (Barcelona)
  7.2 km  Badalona               checked_out  Biblioteca Can Casacuberta - Badalona
 12.1 km  Ripollet               available    Biblioteca Ripollet
 18.4 km  Sabadell               available    Biblioteca Central de Sabadell
```

A igual distancia, un ejemplar disponible sale antes que uno prestado. Los ejemplares que no se
pueden situar salen al final, sin distancia.

## Cómo se sitúa un ejemplar

Un catálogo solo dice en qué biblioteca está el ejemplar. Se busca su municipio así:

1. **Directorio** (`data/libraries.csv`, opcional): `catalog,key,name,municipality`. La `key`
   es el código o nombre exacto que devuelve el catálogo. Es lo más fiable y gana siempre.
   Se ve en la respuesta como `location_source: "directory"`.
2. **Nombre**: si el texto de la biblioteca contiene el nombre de un municipio conocido
   (`Biblioteca Central de Sabadell`), se usa ese. Es una heurística y sale como
   `location_source: "name"`. Se ignoran frases como "Diputació de Barcelona" o "Xarxa de Biblioteques".

Lo que no se puede situar **nunca se pierde en silencio**: la respuesta incluye
`unlocated_libraries` (con cuántos ejemplares tiene cada una) y un `notice`. Con `radius_km`,
`municipality`, `province` o `county` esas bibliotecas se excluyen del resultado, porque no se puede
saber si cumplen el filtro; con solo `near` van al final.

Para mejorarlo, añade a `data/libraries.csv` las bibliotecas del aviso:

```csv
catalog,key,name,municipality
aladi,BSAB,Biblioteca Central de Sabadell,Sabadell
```

## Datos de municipios

- **Incluidos:** `src/spain_libraries_mcp/data/municipalities.csv` trae 21 municipios del área de Barcelona
  con coordenadas **aproximadas** (centro urbano, precisión de ~1 km; columna `approx=1`). Sirven
  para empezar, pero no son datos oficiales.
- **Oficiales para toda Cataluña:**
  [Caps de municipi de Catalunya georeferenciats](https://analisi.transparenciacatalunya.cat/Sector-P-blic/Caps-de-municipi-de-Catalunya-georeferenciats/wpyq-we8x)
  (Generalitat / ICGC). Se descargan con:

  ```bash
  spain-libraries-update-municipalities                              # descarga y sobrescribe el fichero incluido
  spain-libraries-update-municipalities --output ~/municipalities.csv
  export SPAIN_LIBRARIES_MUNICIPALITIES=~/municipalities.csv         # o apunta a tu fichero
  ```

  Los nombres de columna del portal se detectan por palabras clave, se imprimen por `stderr` y el
  script falla con un mensaje claro si no encuentra nombre y coordenadas.
- **Otras comunidades:** el formato es `name,province,county,region,lat,lon,approx`. Añade filas
  con `region` en minúsculas sin acentos (`madrid`, `galicia`…) y funcionará igual.

## Límites conocidos

- La distancia es en línea recta entre centros de municipio, no por carretera ni transporte público.
  Dos bibliotecas del mismo municipio salen a la misma distancia.
- Cada municipio usa un único punto. En Barcelona ciudad no distingue entre barrios.
- Sin directorio, las bibliotecas cuyo nombre no contiene el municipio quedan sin ubicar.
