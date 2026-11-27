"""
Aplicación de consultas y visualización: economía y criminalidad en Costa Rica.

Punto de entrada de la aplicación. Se ejecuta desde la raíz del repositorio con:
    streamlit run app/app.py

Streamlit vuelve a ejecutar este archivo de arriba hacia abajo cada vez que el usuario interactúa
con un control. La barra lateral elige la sección, y cada sección está en su propio módulo:
- pagina_consultas.py: consultas convencionales (búsqueda, operadores lógicos, rangos, filtros, orden)
- pagina_facets.py: consultas con facets (campo, rango, consultas, anidados y estadísticos)
- pagina_geo.py: consultas geoespaciales (proximidad, polígono y polígono con facets)
"""

import streamlit as st
from streamlit_folium import st_folium

import pagina_consultas
import pagina_facets
import pagina_geo
from mapa import agregar_leyenda_colores, agregar_puntos, campos_para_mapa, crear_mapa
from utilidades import (
    ejecutar_select,
    lista_plana_a_tabla,
    mostrar_consulta,
    total_documentos,
    total_encontrados,
    valores_de_campo,
    varios_valores,
)

st.set_page_config(
    page_title="Economía y criminalidad en Costa Rica",
    layout="wide",
)


def pagina_inicio():
    st.title("Economía y criminalidad en Costa Rica")
    st.write(
        "Aplicación para consultar los delitos registrados por el OIJ entre 2019 y 2026, integrados con "
        "los indicadores económicos de cada cantón (Censo 2011 del INEC). Los datos fueron procesados con "
        "Apache Spark e indexados en Apache Solr; todas las consultas de la aplicación las ejecuta Solr."
    )

    total = total_documentos()
    if total is None:
        st.error(
            "No se pudo conectar con Solr. Encienda el contenedor con `docker compose up -d` y, si es la "
            "primera vez, cree el schema e indexe los datos (ver README)."
        )
        return

    # Resumen general con un field facet por tipo de delito.
    respuesta = ejecutar_select({
        "q": "*:*",
        "rows": 0,
        "facet": "true",
        "facet.field": "delito",
        "facet.mincount": 1,
    })
    if respuesta is None:
        return
    tabla = lista_plana_a_tabla(respuesta["facet_counts"]["facet_fields"]["delito"], "Tipo de delito")

    columnas = st.columns(len(tabla) + 1)
    columnas[0].metric("Delitos indexados", f"{total:,}".replace(",", " "))
    posicion = 1
    for indice in tabla.index:
        columnas[posicion].metric(tabla.loc[indice, "Tipo de delito"].title(), f"{tabla.loc[indice, 'Cantidad']:,}".replace(",", " "))
        posicion = posicion + 1

    st.subheader("Mapa de los delitos")
    st.write(
        "Muestra aleatoria de los delitos como puntos sobre el mapa. Cada punto es un delito, ubicado "
        "dentro de su cantón (las coordenadas se generaron en el ETL respetando el cantón)."
    )

    columna_1, columna_2 = st.columns([3, 1])
    with columna_1:
        delitos = st.multiselect("Tipos de delito", valores_de_campo("delito"))
    with columna_2:
        cantidad = st.selectbox("Puntos en la muestra", [500, 1000, 1500, 3000, 5000], index=2)

    filtros = []
    if len(delitos) > 0:
        filtros.append(varios_valores("delito", delitos))

    # sort=random_<semilla> pide a Solr un orden aleatorio (usa el campo dinámico random_* del schema
    # por defecto). Así la muestra no se concentra en los primeros documentos indexados.
    parametros = {
        "q": "*:*",
        "fq": filtros,
        "fl": campos_para_mapa,
        "rows": cantidad,
        "sort": "random_2026 asc",
    }
    respuesta = ejecutar_select(parametros)
    if respuesta is None:
        return

    st.caption(
        "Se dibujan " + str(len(respuesta["response"]["docs"])) + " de "
        + f"{total_encontrados(respuesta):,}".replace(",", " ") + " registros que cumplen el filtro."
    )
    mostrar_consulta(parametros)
    mapa = crear_mapa()
    agregar_puntos(mapa, respuesta["response"]["docs"])
    st_folium(mapa, key="mapa_inicio", height=520, use_container_width=True, returned_objects=[])
    agregar_leyenda_colores(st)


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------
secciones = {
    "Inicio y mapa general": pagina_inicio,
    "Consultas convencionales": pagina_consultas.mostrar_pagina,
    "Consultas con facets": pagina_facets.mostrar_pagina,
    "Consultas geoespaciales": pagina_geo.mostrar_pagina,
}

st.sidebar.title("Navegación")
nombres_secciones = []
for nombre in secciones:
    nombres_secciones.append(nombre)
seccion = st.sidebar.radio("Sección", nombres_secciones)

total = total_documentos()
if total is None:
    st.sidebar.error("Solr: sin conexión")
else:
    st.sidebar.success("Solr conectado: " + f"{total:,}".replace(",", " ") + " documentos")

st.sidebar.caption("Proyecto 2, Bases de Datos II, TEC, 2026")

secciones[seccion]()
