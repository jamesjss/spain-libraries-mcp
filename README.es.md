# spain-libraries-mcp

> **Idioma:** [English](README.md) | Español

Servidor **MCP** (Model Context Protocol) en Python para buscar libros en bibliotecas de España
y saber **en qué bibliotecas hay ejemplares** y, cuando el catálogo lo informa, **si están disponibles**.

No hace scraping: usa los protocolos bibliotecarios estándar que las propias redes publican para
uso por máquina, **Z39.50** y **SRU**.

## Cobertura

| id | Catálogo | Qué cubre | Protocolo |
|---|---|---|---|
| `ccbip` | Catálogo Colectivo de Bibliotecas Públicas | +3.800 bibliotecas públicas: 53 BPE y 16 redes autonómicas | Z39.50 |
| `bne` | Biblioteca Nacional de España | Depósito legal | SRU |
| `rebiun` | REBIUN | Bibliotecas universitarias y CSIC | Z39.50 |
| `csic` | Red de Bibliotecas del CSIC | Institutos CSIC | Z39.50 |
| `aladi` | Aladí (Diputació de Barcelona) | Bibliotecas municipales de la provincia de Barcelona (no está en el CCBIP) | Z39.50 |
| `galicia` | Rede de Bibliotecas Públicas de Galicia | Red pública gallega con disponibilidad | Z39.50 |
| `euskadi` | Red de Lectura Pública de Euskadi | Bibliotecas municipales vascas | Z39.50 |
| `ccpb` | Patrimonio Bibliográfico (inactivo) | Fondo antiguo | Z39.50 |

Detalle, fuentes y limitaciones en [docs/es/catalogos.md](docs/es/catalogos.md).

## Herramientas MCP

- `search_books(title, author, isbn, subject, text, catalogs, region, max_per_catalog, near, radius_km, municipality, province, county)`: busca en paralelo en todos los catálogos activos.
- `locate_holdings(isbn | title, author, catalogs, region, near, radius_km, municipality, province, county, available_only)`: lista las bibliotecas con ejemplares y su estado (`available`, `checked_out`, `not_for_loan`, `unavailable`, `lost`, `unknown`).
- `list_catalogs(region, include_inactive)`: muestra la cobertura y metadatos de conexión.
- `check_catalogs()`: comprueba la conexión con cada servidor (latencia o error).

### Búsqueda por cercanía

`near="Barcelona"` ordena los ejemplares del más cercano al más lejano (con `distance_km`),
y `radius_km`, `municipality`, `province` o `county` (comarca) filtran. Cómo se sitúan las bibliotecas
y qué datos usa: [docs/es/geolocalizacion.md](docs/es/geolocalizacion.md).

## Instalación

Necesita la librería nativa **YAZ** (cliente Z39.50 de Index Data):

```bash
# Debian/Ubuntu
sudo apt install libyaz5
# macOS
brew install yaz
```

Y el paquete:

```bash
pip install .            # o: uv pip install .
spain-libraries-mcp      # stdio (para Claude Desktop / Claude Code)
spain-libraries-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

### Docker (recomendado para el homelab)

```bash
docker compose up -d --build
# endpoint MCP: http://<host>:8000/mcp
```

La imagen ya incluye `libyaz5`. Para Portainer, despliega `docker-compose.yml` como stack.

### Claude Desktop / Claude Code

Ver `examples/claude_desktop_config.json`. En Claude Code:

```bash
claude mcp add spain-libraries -- spain-libraries-mcp
# o vía HTTP
claude mcp add --transport http spain-libraries http://<host>:8000/mcp
```

## Configuración

| Variable | Por defecto | Uso |
|---|---|---|
| `SPAIN_LIBRARIES_TIMEOUT` | `20` | Segundos por catálogo |
| `SPAIN_LIBRARIES_CATALOGS` | — | JSON para añadir, cambiar o activar catálogos (ver `examples/extra-catalogs.json`) |
| `YAZ_LIB` | autodetección | Ruta a `libyaz` si no se encuentra |
| `SPAIN_LIBRARIES_MUNICIPALITIES` | fichero incluido | CSV de municipios con coordenadas (ver `spain-libraries-update-municipalities`) |
| `SPAIN_LIBRARIES_DIRECTORY` | fichero incluido | CSV que relaciona códigos de biblioteca con municipio |
| `MCP_TRANSPORT` / `MCP_HOST` / `MCP_PORT` | `stdio` / `127.0.0.1` / `8000` | Transporte |

## Primer paso tras instalar

Ejecuta la herramienta `check_catalogs`. Los datos de conexión vienen de la documentación
pública de cada red, y algunos (`aladi`, `ccpb`) son antiguos o no oficiales. Si alguno
falla, corrígelo con `SPAIN_LIBRARIES_CATALOGS`.

## Tests

```bash
sudo apt install yaz        # trae yaz-ztest, un servidor Z39.50 de pruebas
pip install -e ".[dev]" && pytest
```

## Uso responsable

Son servidores públicos con recursos limitados: el servidor limita a 2 consultas simultáneas por
catálogo, guarda resultados 5 minutos en caché y no hace volcados masivos. No se consultan las
páginas web de los OPAC (Aladí, por ejemplo, lo prohíbe en su `robots.txt`); en su lugar se
devuelve un enlace de búsqueda para abrirlo a mano.
