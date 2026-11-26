# Arquitectura

> **Idioma:** [English](../architecture.md) | Español

```
Cliente MCP (Claude) ──► server.py (MCPServer, 4 tools)
                               │
                               ▼
                 service.FederatedSearch ── caché 5 min, 2 consultas simultáneas por catálogo
                          │            │
            asyncio.to_thread       async httpx
                  │                    │
              zoom.py (Z39.50)      sru.py (SRU 1.2 / CQL)
        ctypes → libyaz (ZOOM API)     │
                  │                    │
                  └──── MARCXML ───────┘
                           │
                       marc.py ── Book + Holdings (perfiles koha / alma / sierra / absysnet / OPAC)
```

## Módulos

- `catalogs.py`: registro de catálogos (`Catalog`, datos de conexión, cobertura, fuente y si están verificados). Se puede ampliar por JSON.
- `queries.py`: traduce `SearchCriteria` (título, autor, ISBN, materia, texto) a PQF (atributos Bib-1) y CQL.
- `zoom.py`: envoltorio `ctypes` de 13 funciones de la API ZOOM de YAZ. Pide el registro en `raw`, en `xml` (YAZ convierte ISO-8859-1/MARC-8 → UTF-8) y en `opac` cuando se usa esa sintaxis.
- `sru.py`: cliente SRU 1.2; detecta diagnósticos de error.
- `marc.py`: extrae los datos bibliográficos (`Book`) y normaliza los ejemplares (`Holding`) según el sistema de origen.
- `geo.py`: municipios, situación de cada ejemplar (directorio o nombre) y orden por distancia (haversine). Ver [geolocalizacion.md](geolocalizacion.md).
- `updater.py`: genera `data/municipalities.csv` con los datos oficiales de la Generalitat.
- `service.py`: búsqueda federada en paralelo (`FederatedSearch`). Un catálogo caído o lento devuelve su `error` sin afectar a los demás.
- `server.py`: herramientas MCP y arranque (`stdio` o `streamable-http`).

## Decisiones

- **YAZ por `ctypes` y no un cliente Z39.50 en Python puro.** Z39.50 es ASN.1/BER y los servidores reales (AbsysNet, Sierra) tienen peculiaridades. YAZ lleva más de 25 años en producción en Koha, VuFind y otros. No hay bindings Python mantenidos en PyPI.
- **Sin scraping de OPAC.** Es frágil y en algunos casos lo prohíbe el `robots.txt` (Aladí). Se devuelve un enlace al OPAC (`opac_search_url`).
- **mcp 2.x** (`MCPServer`).

## Tests

- `tests/test_geo.py`: prueba la búsqueda por cercanía (orden, radio, comarca, caché sin contaminar y el actualizador de municipios) sin red.
- `tests/test_marc.py`, `tests/test_queries.py`, `tests/test_sru_and_catalogs.py`, `tests/test_service_and_mcp.py`: pruebas unitarias y con mocks de parseo MARC/OPAC, PQF/CQL, SRU, carga de catálogos, reintentos, caché y errores de herramientas MCP.
- `tests/test_libraries.py`: levanta `yaz-ztest` (un servidor Z39.50 real de YAZ) en un puerto libre y prueba el cliente ZOOM, la sintaxis OPAC con disponibilidad, el aislamiento de errores entre catálogos y las tools MCP.
