"""
Consultas con facets: agregaciones que Solr calcula sobre todos los documentos que cumplen la
consulta, sin devolver los documentos (rows = 0).

Se usan las dos formas de pedir facets que ofrece Solr:
- Parámetros clásicos (facet.field, facet.range, facet.query): para facets simples.
- JSON Facet API (parámetro json.facet): permite anidar facets y calcular funciones estadísticas
  (avg, min, max, sum) dentro de cada grupo, que con los parámetros clásicos no se puede.
"""

import json

import pandas as pd
import streamlit as st

from utilidades import (
    ejecutar_select,
    lista_plana_a_tabla,
    mostrar_consulta,
    nombre_legible,
    total_encontrados,
    valor_exacto,
    valores_de_campo,
)

campos_categoricos = [
    "delito",
    "subdelito",
    "provincia",
    "canton",
    "victima",
    "sexo",
    "edad",
    "periodo_dia",
    "dia_semana",
    "economia_predominante",
    "nivel_desempleo",
]


def selector_filtro_delito(clave):
    """Control opcional para limitar el facet a un tipo de delito. Devuelve la lista de filtros fq."""
    opciones = ["Todos"]
    for delito in valores_de_campo("delito"):
        opciones.append(delito)
    delito = st.selectbox("Limitar a un tipo de delito", opciones, key=clave)
    if delito == "Todos":
        return []
    return [valor_exacto("delito", delito)]


# ---------------------------------------------------------------------------
# Facet 1: field facet
# ---------------------------------------------------------------------------
def facet_de_campo():
    st.markdown(
        "**Field facet**: agrupa los registros según los valores de un atributo categórico y cuenta "
        "cuántos hay en cada grupo. Es el equivalente en Solr a `GROUP BY campo` con `COUNT(*)`."
    )
    columna_1, columna_2 = st.columns(2)
    with columna_1:
        campo = st.selectbox("Agrupar por", campos_categoricos, format_func=nombre_legible)
    with columna_2:
        filtros = selector_filtro_delito("filtro_facet_1")

    parametros = {
        "q": "*:*",
        "fq": filtros,
        "rows": 0,
        "facet": "true",
        "facet.field": campo,
        "facet.limit": 25,
        "facet.mincount": 1,
    }
    if st.button("Ejecutar facet", key="ejecutar_f1"):
        respuesta = ejecutar_select(parametros)
        if respuesta is None:
            return
        mostrar_consulta(parametros)
        tabla = lista_plana_a_tabla(respuesta["facet_counts"]["facet_fields"][campo], nombre_legible(campo))
        tabla["Porcentaje"] = (tabla["Cantidad"] / total_encontrados(respuesta) * 100).round(2)
        st.bar_chart(tabla, x=nombre_legible(campo), y="Cantidad", horizontal=True, sort="-Cantidad")
        st.dataframe(tabla, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Facet 2: range facet
# ---------------------------------------------------------------------------
def facet_de_rango():
    st.markdown(
        "**Range facet**: cuenta los registros dentro de intervalos de un campo numérico o de fecha. "
        "Se indica el inicio, el fin y el tamaño de cada intervalo (`gap`). Para fechas, el gap se "
        "escribe con la sintaxis de Solr, por ejemplo `+1YEAR` o `+1MONTH`."
    )
    opciones = {
        "Delitos por año": ("fecha", "2019-01-01T00:00:00Z", "2027-01-01T00:00:00Z", "+1YEAR"),
        "Delitos por mes": ("fecha", "2019-01-01T00:00:00Z", "2026-12-01T00:00:00Z", "+1MONTH"),
        "Delitos por franja horaria (cada 3 horas)": ("hora_inicio", "0", "24", "3"),
        "Delitos según la tasa de desempleo del cantón (intervalos de 0,5 %)": ("tasa_desempleo", "0", "6", "0.5"),
        "Delitos según el % de ocupados en el sector primario (intervalos de 10 %)": ("pct_sector_primario", "0", "70", "10"),
    }
    nombres = []
    for nombre in opciones:
        nombres.append(nombre)

    columna_1, columna_2 = st.columns(2)
    with columna_1:
        eleccion = st.selectbox("Intervalos", nombres)
    with columna_2:
        filtros = selector_filtro_delito("filtro_facet_2")

    campo, inicio, fin, intervalo = opciones[eleccion]
    parametros = {
        "q": "*:*",
        "fq": filtros,
        "rows": 0,
        "facet": "true",
        "facet.range": campo,
        "facet.range.start": inicio,
        "facet.range.end": fin,
        "facet.range.gap": intervalo,
    }
    if st.button("Ejecutar facet", key="ejecutar_f2"):
        respuesta = ejecutar_select(parametros)
        if respuesta is None:
            return
        mostrar_consulta(parametros)
        conteos = respuesta["facet_counts"]["facet_ranges"][campo]["counts"]
        tabla = lista_plana_a_tabla(conteos, "Intervalo")

        # Etiquetas más legibles: las fechas se recortan al año o al mes.
        etiquetas = []
        for valor in tabla["Intervalo"]:
            texto = str(valor)
            if campo == "fecha":
                if intervalo == "+1YEAR":
                    texto = texto[:4]
                else:
                    texto = texto[:7]
            etiquetas.append(texto)
        tabla["Intervalo"] = etiquetas

        # Por mes hay 95 intervalos y se lee mejor como línea; los demás, como barras.
        # sort=False conserva el orden de los intervalos en lugar de ordenarlos por cantidad.
        if campo == "fecha" and intervalo == "+1MONTH":
            st.line_chart(tabla, x="Intervalo", y="Cantidad")
        else:
            st.bar_chart(tabla, x="Intervalo", y="Cantidad", sort=False)
        st.dataframe(tabla, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Facet 3: query facets
# ---------------------------------------------------------------------------
def facet_de_consultas():
    st.markdown(
        "**Query facets**: cada `facet.query` es una condición de búsqueda distinta, y Solr devuelve "
        "cuántos registros cumple cada una, todo en una sola petición. Permite comparar grupos que no "
        "salen de un solo campo, por ejemplo cantones con desempleo alto contra cantones agrícolas."
    )
    condiciones = {
        "Cantones con desempleo ALTO": 'nivel_desempleo:"ALTO"',
        "Cantones con desempleo BAJO": 'nivel_desempleo:"BAJO"',
        "Cantones de economía agrícola (sector primario)": 'economia_predominante:"PRIMARIO"',
        "Cantones de economía de servicios (sector terciario)": 'economia_predominante:"TERCIARIO"',
        "Ocurridos de noche o de madrugada": 'periodo_dia:("NOCHE" OR "MADRUGADA")',
        "Ocurridos en fin de semana": "es_fin_de_semana:true",
        "Víctima mujer": 'sexo:"MUJER"',
        "Ocurridos en un mes anómalo": "mes_anomalo:true",
    }
    filtros = selector_filtro_delito("filtro_facet_3")

    lista_condiciones = []
    for nombre in condiciones:
        lista_condiciones.append(condiciones[nombre])

    parametros = {
        "q": "*:*",
        "fq": filtros,
        "rows": 0,
        "facet": "true",
        "facet.query": lista_condiciones,
    }
    if st.button("Ejecutar facet", key="ejecutar_f3"):
        respuesta = ejecutar_select(parametros)
        if respuesta is None:
            return
        mostrar_consulta(parametros)
        total = total_encontrados(respuesta)
        resultados = respuesta["facet_counts"]["facet_queries"]

        filas = []
        for nombre in condiciones:
            cantidad = resultados.get(condiciones[nombre], 0)
            porcentaje = 0.0
            if total > 0:
                porcentaje = round(cantidad / total * 100, 2)
            filas.append({"Condición": nombre, "Cantidad": cantidad, "Porcentaje del total": porcentaje})
        tabla = pd.DataFrame(filas)

        st.metric("Total de registros considerados", total)
        st.bar_chart(tabla, x="Condición", y="Cantidad", horizontal=True, sort="-Cantidad")
        st.dataframe(tabla, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Facet 4: facets anidados
# ---------------------------------------------------------------------------
def facet_anidado():
    st.markdown(
        "**Facets anidados**: distribución de los registros según **dos** atributos. Con la JSON Facet "
        "API se define un facet de tipo `terms` y, dentro de él, otro facet: para cada valor del "
        "primer atributo, Solr cuenta los valores del segundo. Por ejemplo, para cada tipo de economía "
        "del cantón, cuántos delitos hay de cada tipo."
    )
    columna_1, columna_2 = st.columns(2)
    with columna_1:
        campo_externo = st.selectbox("Primer atributo (filas)", campos_categoricos, index=9, format_func=nombre_legible)
    with columna_2:
        campo_interno = st.selectbox("Segundo atributo (columnas)", campos_categoricos, index=0, format_func=nombre_legible)

    facet_json = {
        "externo": {
            "type": "terms",
            "field": campo_externo,
            "limit": 15,
            "facet": {
                "interno": {"type": "terms", "field": campo_interno, "limit": 15},
            },
        }
    }
    parametros = {"q": "*:*", "rows": 0, "json.facet": json.dumps(facet_json)}

    if st.button("Ejecutar facet", key="ejecutar_f4"):
        if campo_externo == campo_interno:
            st.warning("Elija dos atributos distintos.")
            return
        respuesta = ejecutar_select(parametros)
        if respuesta is None:
            return
        mostrar_consulta(parametros)

        # La respuesta tiene la forma: facets.externo.buckets = [{val, count, interno: {buckets: [...]}}]
        filas = []
        for grupo_externo in respuesta["facets"]["externo"]["buckets"]:
            for grupo_interno in grupo_externo["interno"]["buckets"]:
                filas.append({
                    nombre_legible(campo_externo): grupo_externo["val"],
                    nombre_legible(campo_interno): grupo_interno["val"],
                    "Cantidad": grupo_interno["count"],
                })
        tabla = pd.DataFrame(filas)
        if len(tabla) == 0:
            st.info("La consulta no devolvió grupos.")
            return

        # pivot convierte la tabla larga en una tabla cruzada: filas = primer atributo, columnas = segundo.
        cruzada = tabla.pivot(
            index=nombre_legible(campo_externo),
            columns=nombre_legible(campo_interno),
            values="Cantidad",
        ).fillna(0).astype(int)

        st.bar_chart(cruzada, horizontal=True)
        st.caption("Tabla cruzada (cantidad de registros):")
        st.dataframe(cruzada, width="stretch")


# ---------------------------------------------------------------------------
# Facet 5: facets con funciones estadísticas
# ---------------------------------------------------------------------------
def facet_estadistico():
    st.markdown(
        "**Facets con funciones estadísticas**: para cada grupo, Solr calcula funciones sobre un campo "
        "numérico: promedio (`avg`), mínimo (`min`), máximo (`max`) y suma (`sum`). Se usa la JSON "
        "Facet API, que permite poner estas funciones dentro de cada grupo."
    )
    campos_numericos = [
        "tasa_desempleo",
        "tasa_delitos_anual_1000",
        "pct_sector_primario",
        "pct_sector_terciario",
        "relacion_dependencia",
        "hora_inicio",
        "metodos_anomalia",
    ]
    columna_1, columna_2 = st.columns(2)
    with columna_1:
        campo_grupo = st.selectbox(
            "Agrupar por",
            ["provincia", "delito", "economia_predominante", "nivel_desempleo", "periodo_dia", "victima"],
            format_func=nombre_legible,
        )
    with columna_2:
        campo_numerico = st.selectbox("Calcular estadísticas de", campos_numericos, format_func=nombre_legible)

    facet_json = {
        "grupos": {
            "type": "terms",
            "field": campo_grupo,
            "limit": 20,
            "facet": {
                "promedio": "avg(" + campo_numerico + ")",
                "minimo": "min(" + campo_numerico + ")",
                "maximo": "max(" + campo_numerico + ")",
                "suma": "sum(" + campo_numerico + ")",
            },
        }
    }
    parametros = {"q": "*:*", "rows": 0, "json.facet": json.dumps(facet_json)}

    if st.button("Ejecutar facet", key="ejecutar_f5"):
        respuesta = ejecutar_select(parametros)
        if respuesta is None:
            return
        mostrar_consulta(parametros)

        filas = []
        for grupo in respuesta["facets"]["grupos"]["buckets"]:
            filas.append({
                nombre_legible(campo_grupo): grupo["val"],
                "Registros": grupo["count"],
                "Promedio": round(grupo.get("promedio", 0), 3),
                "Mínimo": round(grupo.get("minimo", 0), 3),
                "Máximo": round(grupo.get("maximo", 0), 3),
                "Suma": round(grupo.get("suma", 0), 1),
            })
        tabla = pd.DataFrame(filas)
        st.caption("Promedio de «" + nombre_legible(campo_numerico) + "» en cada grupo:")
        st.bar_chart(tabla, x=nombre_legible(campo_grupo), y="Promedio", horizontal=True, sort="-Promedio")
        st.dataframe(tabla, width="stretch", hide_index=True)
        st.caption(
            "Nota: los indicadores económicos se repiten en cada delito de un cantón, así que el promedio "
            "por grupo está ponderado por la cantidad de delitos."
        )


facets = [
    ("1. Field facet: conteo por atributo", facet_de_campo),
    ("2. Range facet: conteo por intervalos", facet_de_rango),
    ("3. Query facets: conteo por condiciones", facet_de_consultas),
    ("4. Facets anidados: dos atributos", facet_anidado),
    ("5. Facets con funciones estadísticas", facet_estadistico),
]


def mostrar_pagina():
    st.header("Consultas con facets")
    st.write(
        "Agregaciones calculadas por Solr sobre todos los registros. Sirven para ver cómo se distribuyen "
        "los delitos y para comparar la criminalidad entre cantones con distintas condiciones económicas."
    )

    nombres = []
    for facet in facets:
        nombres.append(facet[0])
    seleccion = st.selectbox("Tipo de facet", nombres)

    st.divider()
    for facet in facets:
        if facet[0] == seleccion:
            facet[1]()
