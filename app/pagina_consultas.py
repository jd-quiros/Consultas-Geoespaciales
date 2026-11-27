"""
Consultas convencionales: búsqueda y filtrado sobre los delitos indexados en Solr.

Cada consulta es una función que dibuja sus controles, arma los parámetros de Solr y muestra los
resultados. Cubren los tipos de operación que pide el enunciado:
- búsqueda por valores de campos categóricos y de texto (consultas 1 y 2),
- operadores lógicos AND, OR y NOT (consultas 3, 4 y 5),
- rangos temporales y numéricos (consultas 6 y 7),
- combinación de condiciones mediante filtros (consulta 8),
- ordenamiento por uno o varios atributos (consulta 9),
- consultas sobre los resultados del análisis del ETL (consultas 10 y 11).

Conceptos de Solr que se usan:
- q: la consulta principal. Solr calcula qué tan relevante es cada documento.
- fq (filter query): un filtro. Solo deja pasar o no deja pasar documentos, sin calcular relevancia,
  y Solr guarda su resultado en caché, por lo que es más rápido para condiciones que se repiten.
- sort: orden de los resultados. rows: cuántos documentos devolver.
"""

import datetime

import streamlit as st

from utilidades import (
    documentos_a_tabla,
    ejecutar_select,
    fecha_solr,
    mostrar_consulta,
    nombre_legible,
    total_encontrados,
    valor_exacto,
    valores_de_campo,
    varios_valores,
)


def mostrar_resultados(parametros):
    """Ejecuta la consulta y muestra el total encontrado, la consulta y la tabla de documentos."""
    respuesta = ejecutar_select(parametros)
    if respuesta is None:
        return
    st.metric("Registros encontrados", f"{total_encontrados(respuesta):,}".replace(",", " "))
    mostrar_consulta(parametros)
    tabla = documentos_a_tabla(respuesta)
    if len(tabla) == 0:
        st.info("La consulta no devolvió registros.")
    else:
        st.caption("Se muestran los primeros " + str(len(tabla)) + " registros.")
        st.dataframe(tabla, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Consulta 1: búsqueda por valor de un campo categórico
# ---------------------------------------------------------------------------
def consulta_por_tipo_de_delito(filas):
    st.markdown(
        "Busca los delitos de un tipo, usando el valor exacto del campo categórico `delito`. "
        "Los resultados se ordenan del más reciente al más antiguo."
    )
    delito = st.selectbox("Tipo de delito", valores_de_campo("delito"))
    parametros = {
        "q": valor_exacto("delito", delito),
        "sort": "fecha desc",
        "rows": filas,
    }
    if st.button("Ejecutar consulta", key="ejecutar_1"):
        mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 2: búsqueda de texto libre
# ---------------------------------------------------------------------------
def consulta_texto_libre(filas):
    st.markdown(
        "Busca palabras en el campo `texto`, que reúne el delito, la víctima, la nacionalidad, la "
        "provincia y el cantón. A diferencia de los campos categóricos, este campo está dividido en "
        "palabras y usa reglas del español, así que `robos` también encuentra `ROBO`. "
        "Con `q.op = AND` deben aparecer todas las palabras escritas."
    )
    texto = st.text_input("Palabras a buscar", value="taxista asalto")
    parametros = {
        "q": "texto:(" + texto + ")",
        "q.op": "AND",
        "sort": "fecha desc",
        "rows": filas,
    }
    if st.button("Ejecutar consulta", key="ejecutar_2"):
        if texto.strip() == "":
            st.warning("Escriba al menos una palabra.")
        else:
            mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 3: operador AND
# ---------------------------------------------------------------------------
def consulta_and(filas):
    st.markdown(
        "Operador **AND**: los registros deben cumplir las dos condiciones a la vez, un tipo de "
        "delito **y** una provincia."
    )
    columna_1, columna_2 = st.columns(2)
    with columna_1:
        delito = st.selectbox("Tipo de delito", valores_de_campo("delito"), key="delito_3")
    with columna_2:
        provincia = st.selectbox("Provincia", valores_de_campo("provincia"), key="provincia_3")
    parametros = {
        "q": valor_exacto("delito", delito) + " AND " + valor_exacto("provincia", provincia),
        "sort": "fecha desc",
        "rows": filas,
    }
    if st.button("Ejecutar consulta", key="ejecutar_3"):
        mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 4: operador OR
# ---------------------------------------------------------------------------
def consulta_or(filas):
    st.markdown(
        "Operador **OR**: los registros pueden ser de **cualquiera** de los cantones seleccionados. "
        "Sirve para comparar zonas, por ejemplo los cantones turísticos de la costa del Pacífico."
    )
    cantones_disponibles = sorted(valores_de_campo("canton"))
    sugeridos = []
    for canton in ["GARABITO", "QUEPOS", "SANTA CRUZ"]:
        if canton in cantones_disponibles:
            sugeridos.append(canton)
    cantones = st.multiselect("Cantones", cantones_disponibles, default=sugeridos)
    parametros = {
        "q": varios_valores("canton", cantones),
        "sort": "fecha desc",
        "rows": filas,
    }
    if st.button("Ejecutar consulta", key="ejecutar_4"):
        if len(cantones) == 0:
            st.warning("Seleccione al menos un cantón.")
        else:
            mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 5: operador NOT
# ---------------------------------------------------------------------------
def consulta_not(filas):
    st.markdown(
        "Operador **NOT**: delitos de un tipo cuyas víctimas **no** son costarricenses. Además se "
        "excluyen las categorías que no indican una nacionalidad (`NO REGISTRADA` y `NO APLICA`), "
        "así quedan solo las víctimas de nacionalidad extranjera conocida."
    )
    delito = st.selectbox("Tipo de delito", valores_de_campo("delito"), key="delito_5")
    consulta = (
        valor_exacto("delito", delito)
        + ' AND NOT nacionalidad:"COSTA RICA"'
        + ' AND NOT nacionalidad:("NO REGISTRADA" OR "NO APLICA")'
    )
    parametros = {"q": consulta, "sort": "fecha desc", "rows": filas}
    if st.button("Ejecutar consulta", key="ejecutar_5"):
        mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 6: rango temporal
# ---------------------------------------------------------------------------
def consulta_rango_fechas(filas):
    st.markdown(
        "Rango **temporal**: delitos ocurridos entre dos fechas. En Solr un rango se escribe "
        "`campo:[inicio TO fin]`; los corchetes indican que ambos extremos se incluyen."
    )
    columna_1, columna_2, columna_3 = st.columns(3)
    with columna_1:
        inicio = st.date_input("Desde", value=datetime.date(2020, 3, 16), min_value=datetime.date(2019, 1, 1))
    with columna_2:
        fin = st.date_input("Hasta", value=datetime.date(2020, 5, 31), min_value=datetime.date(2019, 1, 1))
    with columna_3:
        opciones = ["Todos"]
        for delito in valores_de_campo("delito"):
            opciones.append(delito)
        delito = st.selectbox("Tipo de delito", opciones, key="delito_6")

    consulta = "fecha:[" + fecha_solr(inicio) + " TO " + fecha_solr(fin, fin_del_dia=True) + "]"
    if delito != "Todos":
        consulta = consulta + " AND " + valor_exacto("delito", delito)
    parametros = {"q": consulta, "sort": "fecha asc", "rows": filas}

    st.caption("Ejemplo: el rango por defecto corresponde a los primeros meses de restricciones por la pandemia.")
    if st.button("Ejecutar consulta", key="ejecutar_6"):
        if inicio > fin:
            st.warning("La fecha inicial debe ser anterior a la final.")
        else:
            mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 7: rango numérico
# ---------------------------------------------------------------------------
def consulta_rango_desempleo(filas):
    st.markdown(
        "Rango **numérico**: delitos ocurridos en cantones cuya tasa de desempleo (Censo 2011) está "
        "dentro del rango elegido. Relaciona directamente la criminalidad con la economía del cantón."
    )
    # En el Censo 2011 ningún cantón llega a 6 % de desempleo, así que el control va de 0 % a 6 %.
    minimo, maximo = st.slider("Tasa de desempleo del cantón (%)", 0.0, 6.0, (4.0, 6.0), step=0.25)
    parametros = {
        "q": "tasa_desempleo:[" + str(minimo) + " TO " + str(maximo) + "]",
        "sort": "tasa_desempleo desc, fecha desc",
        "rows": filas,
    }
    if st.button("Ejecutar consulta", key="ejecutar_7"):
        mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 8: combinación de condiciones con filtros
# ---------------------------------------------------------------------------
def consulta_filtros_combinados(filas):
    st.markdown(
        "**Combinación de filtros**: cada condición se envía como un `fq` separado. Solr aplica todos "
        "los filtros (equivale a unirlos con AND) y guarda cada uno en caché, de modo que si se repite "
        "una condición la siguiente consulta es más rápida. Las condiciones vacías no se aplican."
    )
    columna_1, columna_2 = st.columns(2)
    with columna_1:
        delitos = st.multiselect("Tipos de delito", valores_de_campo("delito"), default=["ASALTO"])
        sexos = st.multiselect("Sexo de la víctima", valores_de_campo("sexo"), default=["MUJER"])
    with columna_2:
        periodos = st.multiselect("Periodo del día", valores_de_campo("periodo_dia"), default=["NOCHE"])
        solo_fin_de_semana = st.checkbox("Solo fines de semana", value=True)

    filtros = []
    if len(delitos) > 0:
        filtros.append(varios_valores("delito", delitos))
    if len(sexos) > 0:
        filtros.append(varios_valores("sexo", sexos))
    if len(periodos) > 0:
        filtros.append(varios_valores("periodo_dia", periodos))
    if solo_fin_de_semana:
        filtros.append("es_fin_de_semana:true")

    parametros = {"q": "*:*", "fq": filtros, "sort": "fecha desc", "rows": filas}
    if st.button("Ejecutar consulta", key="ejecutar_8"):
        mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 9: ordenamiento por varios atributos
# ---------------------------------------------------------------------------
def consulta_ordenamiento(filas):
    st.markdown(
        "**Ordenamiento** por uno o varios atributos: Solr ordena por el primer criterio y, cuando dos "
        "registros empatan, usa el segundo. Por ejemplo: primero los cantones con más desempleo y, "
        "dentro de cada cantón, los delitos más recientes."
    )
    campos_orden = [
        "tasa_desempleo",
        "tasa_delitos_anual_1000",
        "pct_sector_primario",
        "fecha",
        "hora_inicio",
        "canton",
        "delito",
    ]
    columna_1, columna_2, columna_3, columna_4 = st.columns(4)
    with columna_1:
        campo_1 = st.selectbox("Ordenar primero por", campos_orden, index=0, format_func=nombre_legible)
    with columna_2:
        direccion_1 = st.radio("Dirección", ["desc", "asc"], key="direccion_1", horizontal=True)
    with columna_3:
        campo_2 = st.selectbox("Y luego por", campos_orden, index=3, format_func=nombre_legible)
    with columna_4:
        direccion_2 = st.radio("Dirección", ["desc", "asc"], key="direccion_2", horizontal=True)

    delito = st.selectbox("Tipo de delito", valores_de_campo("delito"), key="delito_9")
    parametros = {
        "q": valor_exacto("delito", delito),
        "sort": campo_1 + " " + direccion_1 + ", " + campo_2 + " " + direccion_2,
        "rows": filas,
    }
    if st.button("Ejecutar consulta", key="ejecutar_9"):
        mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 10: meses anómalos
# ---------------------------------------------------------------------------
def consulta_meses_anomalos(filas):
    st.markdown(
        "Delitos ocurridos en un **cantón y mes anómalo**, según la detección de anomalías del ETL "
        "(marcado por al menos dos de los tres métodos: Z-score, K-Means y PCA). Se ordenan por la "
        "cantidad de métodos que marcaron el mes y luego por fecha."
    )
    opciones = ["Todas"]
    for economia in valores_de_campo("economia_predominante"):
        opciones.append(economia)
    economia = st.selectbox("Economía predominante del cantón", opciones)

    filtros = ["mes_anomalo:true"]
    if economia != "Todas":
        filtros.append(valor_exacto("economia_predominante", economia))
    parametros = {
        "q": "*:*",
        "fq": filtros,
        "sort": "metodos_anomalia desc, fecha desc",
        "rows": filas,
    }
    if st.button("Ejecutar consulta", key="ejecutar_10"):
        mostrar_resultados(parametros)


# ---------------------------------------------------------------------------
# Consulta 11: transparencia del tratamiento de faltantes
# ---------------------------------------------------------------------------
def consulta_datos_imputados(filas):
    st.markdown(
        "Registros cuyo sexo o edad fueron **imputados** durante el ETL. Permite revisar los valores "
        "que no venían en los datos originales. Usa los campos booleanos `sexo_imputado` y "
        "`edad_imputada` unidos con **OR**."
    )
    parametros = {
        "q": "sexo_imputado:true OR edad_imputada:true",
        "sort": "fecha desc",
        "rows": filas,
    }
    if st.button("Ejecutar consulta", key="ejecutar_11"):
        mostrar_resultados(parametros)


# Lista de consultas que aparece en el selector: (nombre, función que la dibuja).
consultas = [
    ("1. Búsqueda por tipo de delito (campo categórico)", consulta_por_tipo_de_delito),
    ("2. Búsqueda de texto libre", consulta_texto_libre),
    ("3. Operador AND: delito y provincia", consulta_and),
    ("4. Operador OR: varios cantones", consulta_or),
    ("5. Operador NOT: víctimas extranjeras", consulta_not),
    ("6. Rango temporal: entre dos fechas", consulta_rango_fechas),
    ("7. Rango numérico: tasa de desempleo del cantón", consulta_rango_desempleo),
    ("8. Combinación de filtros (fq)", consulta_filtros_combinados),
    ("9. Ordenamiento por varios atributos", consulta_ordenamiento),
    ("10. Delitos en meses anómalos", consulta_meses_anomalos),
    ("11. Registros con datos imputados", consulta_datos_imputados),
]


def mostrar_pagina():
    st.header("Consultas convencionales")
    st.write(
        "Consultas de búsqueda y filtrado sobre los delitos indexados. Elija una consulta, ajuste sus "
        "parámetros y ejecútela. Cada resultado muestra la consulta exacta que se envió a Solr."
    )

    nombres = []
    for consulta in consultas:
        nombres.append(consulta[0])

    columna_1, columna_2 = st.columns([3, 1])
    with columna_1:
        seleccion = st.selectbox("Consulta", nombres)
    with columna_2:
        filas = st.selectbox("Registros a mostrar", [10, 20, 50, 100], index=1)

    st.divider()
    for consulta in consultas:
        if consulta[0] == seleccion:
            consulta[1](filas)
