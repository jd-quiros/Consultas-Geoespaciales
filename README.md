# Consultas Geoespaciales: economía y criminalidad en Costa Rica

Proyecto #2 del curso **Bases de Datos II** (IC-4302), Instituto Tecnológico de Costa Rica,
sede Alajuela, II Semestre 2026. Profesora: María Auxiliadora Mora.

**Integrantes:**
- José David Quirós González
- Carlos Andrés Zúñiga Herrera

## Descripción

El proyecto analiza la relación entre los indicadores económicos de los cantones de Costa Rica y
los delitos registrados por el Organismo de Investigación Judicial (OIJ). Tiene dos etapas:

1. **ETL con Apache Spark:** extracción, limpieza, imputación, generación de coordenadas,
   integración de los datasets, detección de anomalías y preparación de los datos para Solr.
2. **Consultas con Apache Solr:** indexación de los datos y una aplicación que permite hacer
   consultas convencionales, consultas con facets y consultas geoespaciales (por radio y por
   polígono) sobre un mapa.

## Fuentes de datos

| Dataset | Fuente | Uso |
|---|---|---|
| `Estadisticas.csv` | [OIJ, estadísticas policiales](https://pjenlinea3.poder-judicial.go.cr/estadisticasoij/) (2019-2026) | Dataset principal: 241 498 delitos |
| `censo2011_empleo.xls` | [INEC, Censo 2011, Cuadro 22](https://admin.inec.cr/sites/default/files/media/reempleocenso2011-22.xls_2.xls) | Indicadores económicos por cantón |
| `cantones.geojson` | [geoBoundaries](https://www.geoboundaries.org), Costa Rica ADM2 | Polígonos de los cantones, para generar coordenadas |

## Estructura del repositorio

```
.
├── docker-compose.yml          # Apache Solr 9 en Docker
├── solr/
│   └── lib/
│       └── jts-core-1.19.0.jar # Librería JTS: permite consultas con polígonos en Solr
└── etl/
    ├── ETL_Crimen_Economia.ipynb   # Notebook de la Etapa 1 (Spark)
    ├── datos/                      # Datos de entrada
    │   ├── Estadisticas.csv
    │   ├── censo2011_empleo.xls
    │   └── cantones.geojson
    └── salida/                     # Resultados del ETL
        ├── anomalias_mensuales.csv
        ├── datos_limpios.csv       # (no se sube al repo, se genera con el notebook)
        └── datos_solr.jsonl        # (no se sube al repo, se genera con el notebook)
```

## Etapa 1: ETL con Spark

El notebook `etl/ETL_Crimen_Economia.ipynb` contiene todo el proceso, con la explicación de cada
paso y sus resultados.

### Ejecución en Google Colab

1. En Google Drive, crear la carpeta `BD2-Proyecto2/datos` y subir ahí los tres archivos de
   `etl/datos/`.
2. Abrir el notebook en Colab y ejecutar todas las celdas (*Entorno de ejecución → Ejecutar todo*).
3. Los resultados quedan en `BD2-Proyecto2/salida` en Drive.

### Ejecución local

Desde la carpeta `etl/`, con Java 17 o superior instalado:

```bash
pip install pyspark==4.3.0 xlrd pandas matplotlib shapely pyarrow jupyter
jupyter notebook ETL_Crimen_Economia.ipynb
```

El notebook detecta que no está en Colab y usa las carpetas `datos/`, `intermedio/` y `salida/`
junto a él.

### Resumen de resultados

- 240 683 delitos limpios e integrados con los indicadores de 81 cantones del censo, sin perder
  registros en el join.
- Cada delito tiene una coordenada aleatoria dentro del polígono real de su cantón.
- Tres algoritmos de detección de anomalías (Z-score, K-Means y PCA) aplicados sobre tasas
  mensuales por cantón, con su comparación.
- Los cantones con mayor desempleo tienen casi el doble de criminalidad que los de menor
  desempleo.

## Etapa 2: Solr

### Levantar Solr

Se necesita Docker (por ejemplo, [OrbStack](https://orbstack.dev) en macOS).

```bash
docker compose up -d
```

El panel de administración queda en http://localhost:8983. Al iniciar se crea el core `crimen`.

Para apagarlo:

```bash
docker compose stop    # apaga el contenedor; se vuelve a encender con "docker compose start"
docker compose down    # apaga y elimina el contenedor (los datos indexados se conservan)
```

La imagen oficial de Solr no incluye la librería JTS, necesaria para consultar con polígonos
arbitrarios. Por eso `docker-compose.yml` monta `solr/lib/jts-core-1.19.0.jar` dentro del
contenedor.
