"""
Consultas geoespaciales sobre el campo "ubicacion" (tipo location_jts en Solr).

1. Proximidad: delitos a una distancia máxima de un punto elegido en el mapa.
   Usa el filtro {!geofilt}, que recibe el campo espacial (sfield), el punto (pt) y la distancia
   en kilómetros (d).
2. Polígono: delitos dentro de un polígono dibujado por el usuario.
   El polígono se convierte a WKT y se envía con el parser {!field}:
   ubicacion:Intersects(POLYGON((...))). El filtrado lo hace Solr con su índice espacial; la
   aplicación solo recibe los documentos que están dentro.
3. Polígono con facets: el mismo filtro por polígono, más facets y estadísticas sobre los
   delitos de esa región, y la opción de combinarlo con condiciones sobre otros atributos.
"""

import json

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from mapa import (
    agregar_herramienta_dibujo,
    agregar_leyenda_colores,
    agregar_puntos,
    campos_para_mapa,
    crear_mapa,
    dibujar_poligono,
    obtener_poligono_dibujado,
    poligono_a_wkt,
)
from utilidades import (
    ejecutar_select,
    lista_plana_a_tabla,
    mostrar_consulta,
    total_encontrados,
    valores_de_campo,
    varios_valores,
)
import folium


def controles_atributos(clave):
    """
    Controles para combinar el filtro geoespacial con condiciones sobre otros atributos.
    Devuelve la lista de filtros fq que se agregan a la consulta.
    """
    columna_1, columna_2 = st.columns(2)
    with columna_1:
        delitos = st.multiselect("Tipos de delito (opcional)", valores_de_campo("delito"), key="delitos_" + clave)
    with columna_2:
        periodos = st.multiselect("Periodo del día (opcional)", valores_de_campo("periodo_dia"), key="periodos_" + clave)

    filtros = []
    if len(delitos) > 0:
        filtros.append(varios_valores("delito", delitos))
    if len(periodos) > 0:
        filtros.append(varios_valores("periodo_dia", periodos))
    return filtros


def mostrar_conteo_por_delito(respuesta):
    """Muestra el field facet por tipo de delito que acompaña a las consultas geoespaciales."""
    tabla = lista_plana_a_tabla(respuesta["facet_counts"]["facet_fields"]["delito"], "Tipo de delito")
    if len(tabla) > 0:
        st.bar_chart(tabla, x="Tipo de delito", y="Cantidad", horizontal=True, sort="-Cantidad")


# ---------------------------------------------------------------------------
# Consulta geoespacial 1: proximidad a un punto
# ---------------------------------------------------------------------------
def consulta_proximidad(maximo_puntos):
    st.markdown(
        "Haga **clic en el mapa** para elegir el punto central y defina el **radio** en kilómetros. "
        "Solr devuelve los delitos cuya ubicación está a esa distancia o menos del punto. Opcionalmente "
        "se puede combinar con condiciones sobre el tipo de delito y el periodo del día."
    )

    if "centro_proximidad" not in st.session_state:
        st.session_state["centro_proximidad"] = [9.9333, -84.0833]
    centro = st.session_state["centro_proximidad"]

    columna_mapa, columna_controles = st.columns([3, 2])
    with columna_controles:
        radio = st.slider("Radio (km)", 1, 50, 5)
        st.write("Punto central: **" + str(round(centro[0], 4)) + ", " + str(round(centro[1], 4)) + "**")
        filtros = controles_atributos("proximidad")

    with columna_mapa:
        mapa_seleccion = crear_mapa()
        folium.Marker(centro, tooltip="Punto central").add_to(mapa_seleccion)
        folium.Circle(centro, radius=radio * 1000, color="#1f77b4", fill=False).add_to(mapa_seleccion)
        estado = st_folium(mapa_seleccion, key="mapa_proximidad", height=420, use_container_width=True, returned_objects=["last_clicked"])

    # Si el usuario hizo clic en otro punto, se guarda y se vuelve a dibujar la página.
    if estado is not None and estado.get("last_clicked") is not None:
        nuevo_centro = [estado["last_clicked"]["lat"], estado["last_clicked"]["lng"]]
        if nuevo_centro != centro:
            st.session_state["centro_proximidad"] = nuevo_centro
            st.rerun()

    filtro_espacial = "{!geofilt sfield=ubicacion pt=" + str(centro[0]) + "," + str(centro[1]) + " d=" + str(radio) + "}"
    todos_los_filtros = [filtro_espacial]
    for filtro in filtros:
        todos_los_filtros.append(filtro)

    parametros = {
        "q": "*:*",
        "fq": todos_los_filtros,
        "fl": campos_para_mapa,
        "rows": maximo_puntos,
        "facet": "true",
        "facet.field": "delito",
        "facet.mincount": 1,
    }

    if st.button("Ejecutar consulta por proximidad", type="primary"):
        respuesta = ejecutar_select(parametros)
        if respuesta is not None:
            st.session_state["resultado_proximidad"] = (parametros, respuesta, centro, radio)

    if "resultado_proximidad" in st.session_state:
        parametros_guardados, respuesta, centro_usado, radio_usado = st.session_state["resultado_proximidad"]
        mostrar_resultado_mapa(parametros_guardados, respuesta, centro_mapa=centro_usado, radio=radio_usado)
        mostrar_conteo_por_delito(respuesta)


# ---------------------------------------------------------------------------
# Consulta geoespacial 2: dentro de un polígono
# ---------------------------------------------------------------------------
def consulta_poligono(maximo_puntos):
    st.markdown(
        "Use la herramienta de dibujo (a la izquierda del mapa) para **dibujar un polígono**: haga clic "
        "en cada vértice y termine haciendo clic en el primero. Luego ejecute la consulta: la aplicación "
        "convierte el polígono a formato WKT y Solr devuelve solo los delitos que están dentro."
    )
    filtros = controles_atributos("poligono")
    vertices = mapa_de_dibujo("mapa_poligono")

    if st.button("Ejecutar consulta por polígono", type="primary"):
        if vertices is None:
            st.warning("Primero dibuje un polígono en el mapa.")
        else:
            wkt = poligono_a_wkt(vertices)
            todos_los_filtros = ["{!field f=ubicacion}Intersects(" + wkt + ")"]
            for filtro in filtros:
                todos_los_filtros.append(filtro)
            parametros = {
                "q": "*:*",
                "fq": todos_los_filtros,
                "fl": campos_para_mapa,
                "rows": maximo_puntos,
                "facet": "true",
                "facet.field": "delito",
                "facet.mincount": 1,
            }
            respuesta = ejecutar_select(parametros)
            if respuesta is not None:
                st.session_state["resultado_poligono"] = (parametros, respuesta, vertices)

    if "resultado_poligono" in st.session_state:
        parametros_guardados, respuesta, vertices_usados = st.session_state["resultado_poligono"]
        mostrar_resultado_mapa(parametros_guardados, respuesta, vertices=vertices_usados)
        mostrar_conteo_por_delito(respuesta)


# ---------------------------------------------------------------------------
# Consulta geoespacial 3: polígono combinado con facets
# ---------------------------------------------------------------------------
def consulta_poligono_con_facets(maximo_puntos):
    st.markdown(
        "Combina el **filtro por polígono** con **facets**: además de los puntos, Solr calcula para la "
        "región dibujada cuántos delitos hay de cada tipo, en qué periodo del día ocurren, en qué "
        "cantones, y el promedio de los indicadores económicos de la zona. Así se puede comparar la "
        "criminalidad y la economía de dos regiones dibujando una y luego la otra."
    )
    filtros = controles_atributos("poligono_facets")
    vertices = mapa_de_dibujo("mapa_poligono_facets")

    if st.button("Ejecutar consulta con facets", type="primary"):
        if vertices is None:
            st.warning("Primero dibuje un polígono en el mapa.")
        else:
            wkt = poligono_a_wkt(vertices)
            todos_los_filtros = ["{!field f=ubicacion}Intersects(" + wkt + ")"]
            for filtro in filtros:
                todos_los_filtros.append(filtro)

            facet_json = {
                "por_delito": {"type": "terms", "field": "delito", "limit": 10},
                "por_periodo": {"type": "terms", "field": "periodo_dia", "limit": 4},
                "por_canton": {"type": "terms", "field": "canton", "limit": 10},
                "por_economia": {"type": "terms", "field": "economia_predominante", "limit": 3},
                "desempleo_promedio": "avg(tasa_desempleo)",
                "tasa_delitos_promedio": "avg(tasa_delitos_anual_1000)",
                "primario_promedio": "avg(pct_sector_primario)",
                "cantones_distintos": "unique(canton)",
            }
            parametros = {
                "q": "*:*",
                "fq": todos_los_filtros,
                "fl": campos_para_mapa,
                "rows": maximo_puntos,
                "json.facet": json.dumps(facet_json),
            }
            respuesta = ejecutar_select(parametros)
            if respuesta is not None:
                st.session_state["resultado_poligono_facets"] = (parametros, respuesta, vertices)

    if "resultado_poligono_facets" in st.session_state:
        parametros_guardados, respuesta, vertices_usados = st.session_state["resultado_poligono_facets"]
        mostrar_resultado_mapa(parametros_guardados, respuesta, vertices=vertices_usados)
        mostrar_facets_region(respuesta)


def mostrar_facets_region(respuesta):
    """Muestra los facets y las estadísticas calculadas por Solr para la región dibujada."""
    facets = respuesta.get("facets", {})
    if facets.get("count", 0) == 0:
        return

    columna_1, columna_2, columna_3, columna_4 = st.columns(4)
    columna_1.metric("Cantones en la región", facets.get("cantones_distintos", 0))
    columna_2.metric("Desempleo promedio (%)", round(facets.get("desempleo_promedio", 0), 2))
    columna_3.metric("Delitos al año por 1000 hab.", round(facets.get("tasa_delitos_promedio", 0), 2))
    columna_4.metric("% en sector primario", round(facets.get("primario_promedio", 0), 2))

    grupos = [
        ("por_delito", "Tipo de delito"),
        ("por_periodo", "Periodo del día"),
        ("por_canton", "Cantón"),
        ("por_economia", "Economía predominante"),
    ]
    columnas = st.columns(2)
    posicion = 0
    for clave, titulo in grupos:
        filas = []
        for grupo in facets.get(clave, {}).get("buckets", []):
            filas.append({titulo: grupo["val"], "Cantidad": grupo["count"]})
        with columnas[posicion % 2]:
            st.caption(titulo)
            if len(filas) > 0:
                st.bar_chart(pd.DataFrame(filas), x=titulo, y="Cantidad", horizontal=True, height=250, sort="-Cantidad")
        posicion = posicion + 1


# ---------------------------------------------------------------------------
# Partes comunes
# ---------------------------------------------------------------------------
def mapa_de_dibujo(clave):
    """Muestra el mapa con la herramienta de dibujo y devuelve los vértices del último polígono."""
    mapa_dibujo = crear_mapa()
    agregar_herramienta_dibujo(mapa_dibujo)
    estado = st_folium(mapa_dibujo, key=clave, height=450, use_container_width=True, returned_objects=["all_drawings"])
    vertices = obtener_poligono_dibujado(estado)
    if vertices is None:
        st.caption("Todavía no hay ningún polígono dibujado.")
    else:
        st.caption("Polígono dibujado con " + str(len(vertices) - 1) + " vértices.")
    return vertices


def mostrar_resultado_mapa(parametros, respuesta, vertices=None, centro_mapa=None, radio=None):
    """
    Muestra el resultado de una consulta geoespacial: el total encontrado, la consulta enviada y un
    mapa con únicamente los puntos que devolvió Solr.
    """
    st.subheader("Resultado")
    total = total_encontrados(respuesta)
    documentos = respuesta["response"]["docs"]

    columna_1, columna_2 = st.columns(2)
    columna_1.metric("Registros encontrados por Solr", f"{total:,}".replace(",", " "))
    columna_2.metric("Puntos dibujados en el mapa", f"{len(documentos):,}".replace(",", " "))
    if total > len(documentos):
        st.caption(
            "El mapa dibuja como máximo la cantidad de puntos elegida en la barra lateral, para que "
            "se mantenga fluido. El total encontrado corresponde a todos los registros dentro del área."
        )
    mostrar_consulta(parametros)

    mapa_resultado = crear_mapa(centro=centro_mapa, zoom=11 if centro_mapa is not None else 8)
    if vertices is not None:
        dibujar_poligono(mapa_resultado, vertices)
    if centro_mapa is not None and radio is not None:
        folium.Circle(centro_mapa, radius=radio * 1000, color="#1f77b4", fill=False).add_to(mapa_resultado)
    agregar_puntos(mapa_resultado, documentos)

    # fit_bounds ajusta el acercamiento del mapa para que se vea toda el área consultada.
    if vertices is not None:
        latitudes = []
        longitudes = []
        for vertice in vertices:
            longitudes.append(vertice[0])
            latitudes.append(vertice[1])
        mapa_resultado.fit_bounds([[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]])

    st_folium(mapa_resultado, key="resultado_" + str(id(respuesta)), height=450, use_container_width=True, returned_objects=[])
    agregar_leyenda_colores(st)


consultas_geo = [
    ("1. Proximidad a un punto (radio)", consulta_proximidad),
    ("2. Dentro de un polígono dibujado", consulta_poligono),
    ("3. Polígono combinado con facets", consulta_poligono_con_facets),
]


def mostrar_pagina():
    st.header("Consultas geoespaciales")
    st.write(
        "Consultas sobre la ubicación de los delitos. El filtrado espacial lo ejecuta Solr con su índice "
        "espacial (tipo SpatialRecursivePrefixTreeFieldType con JTS): la aplicación solo recibe y dibuja "
        "los registros que cumplen el filtro."
    )

    nombres = []
    for consulta in consultas_geo:
        nombres.append(consulta[0])
    seleccion = st.selectbox("Consulta geoespacial", nombres)

    maximo_puntos = st.sidebar.slider("Máximo de puntos a dibujar", 500, 10000, 3000, step=500)

    st.divider()
    for consulta in consultas_geo:
        if consulta[0] == seleccion:
            consulta[1](maximo_puntos)
