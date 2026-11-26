# Catálogos y cómo se accede a ellos

> **Idioma:** [English](../catalogs.md) | Español

## Por qué no hay "un único catálogo de España"

En España no hay una base de datos única con todos los ejemplares. Hay catálogos colectivos que
agregan redes, y cada red usa su propio sistema de gestión (AbsysNet, Koha, Sierra, Alma…).
La vía estándar para que una máquina los consulte es **Z39.50** (protocolo binario, puerto TCP)
y, en algunos casos, **SRU** (lo mismo sobre HTTP).

La estrategia del proyecto:

1. **CCBIP** como columna vertebral: agrega las 16 redes autonómicas y las 53 BPE.
2. **Catálogos que no están en el CCBIP o que dan más detalle** se consultan aparte:
   Aladí (Barcelona), Galicia (disponibilidad por ejemplar), Euskadi, BNE, REBIUN y CSIC.

## Datos de conexión

| id | Host | Puerto | Base | Juego de caracteres | Fuente | Verificado |
|---|---|---|---|---|---|---|
| ccbip | catalogos.mecd.es | 212 | ABNET_DB | ISO-8859-1 | [Folleto CCBIP 2021](https://www.cultura.gob.es/dam/jcr:3dece3fd-d232-440a-9f17-0427b75fba21/folleto-ccbip-2021.pdf), [España es Cultura](https://www.españaescultura.es/datos-abiertos/z39-50.html) | Sí (doc. oficial) |
| bne | https://catalogo.bne.es/view/sru/34BNE_INST | – | SRU 1.2, CQL `alma.*` | UTF-8 | [BNE – Descarga SRU](https://bne.es/en/profiles/librarians/record-supply/descarga-sru) | Sí |
| bne (alt.) | z3950.bne.es | 210 | 34BNE_INST | UTF-8 | [BNE – Descarga Z39.50](https://www.bne.es/es/perfiles/bibliotecarios/suministro-registros/descarga-z3950) | Sí |
| rebiun | rebiun.crue.org | 210 | ABSYSREBIUN | – | [Manual REBIUN 2017](https://www.rebiun.org/sites/default/files/2017-11/Provisional_Manual%20de%20procedimiento%20%20REBIUN_corregido_oct17.pdf) | Sí |
| csic | eu00.alma.exlibrisgroup.com | 1921 | 34CSIC_INST | UTF-8 | [CSIC](https://sitios.csic.es/web/red-de-bibliotecas/servidor-z3950) | Sí |
| aladi | aladi.diba.cat | 210 | INNOPAC | – | Proyecto [abematt/aladi-catalogue](https://github.com/abematt/aladi-catalogue) | No oficial |
| galicia | z3950-rbgalicia.xunta.gal | 9998 | biblios | UTF-8 | [RBGalicia](https://rbgalicia.xunta.gal/es/catalogo-de-la-red-de-bibliotecas-publicas-de-galicia) | Sí |
| euskadi | z39-katalogoak.euskadi.eus | 2210 | ABNET_DB_CATA (usuario `z3950`) | – | [Euskadi.eus](https://www.euskadi.eus/catalogo-en-linea-opac/web01-a2libzer/es/) | Sí |
| ccpb | ccpb.mcu.es | 210 | absysccpb | – | Correo Bibliotecario (antiguo) | No, inactivo |

Nota: la página de REBECA cita `catalogos.cultura.gob.es`, así que es probable que el dominio
`mecd.es` esté migrando a `cultura.gob.es`. Si `ccbip` falla, prueba a cambiar el host.

## Cobertura del CCBIP por comunidad

Según el folleto oficial: Andalucía, Aragón, Asturias, Canarias, Cantabria, Castilla y León,
Castilla-La Mancha, Cataluña (solo **Argus**: Girona, Lleida, Tarragona), Madrid, Navarra,
C. Valenciana, Extremadura, Galicia, La Rioja, Euskadi y Murcia.
**Baleares, Ceuta y Melilla** solo aportan sus Bibliotecas Públicas del Estado.
La provincia de **Barcelona (Aladí)** no está, y por eso hay un adaptador propio.

## Disponibilidad (prestado / en estantería)

Es lo más difícil y depende del servidor:

- **Sintaxis OPAC de Z39.50**: si el servidor la admite, devuelve `<holdings>` con
  `availableNow`. El MCP la pide primero en `locate_holdings` y, si falla, repite en MARC.
- **Koha (Galicia)**: el campo 952 trae biblioteca, signatura y fecha de préstamo (`$q`).
- **Alma (BNE, CSIC)**: el campo AVA trae biblioteca, total y no disponibles.
- **Sierra (Aladí)**: 907 `$i` indica las bibliotecas con ejemplar, sin estado.
- **AbsysNet (CCBIP, REBIUN, Euskadi)**: depende de la instalación. Se devuelven en bruto los
  campos 850/852/949/999 que lleguen. Si no llega nada, se da el enlace al OPAC.

Cuando el estado (`status`) es `unknown` el libro **está** en esa biblioteca, pero el catálogo no dice
si está prestado.

## Añadir más catálogos

Muchas universidades y redes publican su servidor Z39.50 (buscar "parámetros Z39.50" + nombre).
Se añaden sin tocar código con un JSON en `SPAIN_LIBRARIES_CATALOGS`; ver
`examples/extra-catalogs.json`. Campos clave: `host`, `port`, `database`, `charset`
(`utf-8`, `iso-8859-1`, `marc8`) y `holdings_profile` (`koha`, `alma`, `sierra`, `absysnet`).

La BNE, REBIUN y el CSIC cuentan como catálogos nacionales: entran en cualquier búsqueda por `region` o por `near`.

## Notas de compatibilidad (0.2.1)

- **Aladí (Sierra/INNOPAC):** exige posición explícita cuando se usa estructura de palabras. El catálogo lleva `pqf_extra="@attr 3=3"`.
- **Reintentos de atributos:** ante errores Z39.50 113–123 se repite la consulta con menos atributos (ver `queries.to_pqf`, parámetro `variant`).
- **CCBIP:** `catalogos.mecd.es:212` tarda mucho o no responde desde algunas redes. Timeout propio de 45 s. Si persiste, probar otro host sobrescribiendo el catálogo con `SPAIN_LIBRARIES_CATALOGS` (JSON). El campo `timeout` también puede fijarse ahí.
- **REBIUN:** verificado (`rebiun.crue.org:210`, `ABSYSREBIUN`).
