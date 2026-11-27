"""
Funciones compartidas por todas las páginas de la aplicación:
- ejecutar consultas en Solr y manejar los errores,
- armar las partes de una consulta (valores exactos, rangos),
- convertir las respuestas de Solr en tablas de pandas,
- mostrar en pantalla la consulta que se envió.
"""

import json
import os
import sys

import pandas as pd
import streamlit as st

# El módulo cliente_solr está en la carpeta solr/ del repositorio. Se agrega esa carpeta a las rutas
# de búsqueda de Python para poder importarlo y no repetir el código de conexión.
carpeta_app = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(carpeta_app, "..", "solr"))

from cliente_solr import ErrorSolr, url_core, obtener_json, enviar_json  # noqa: E402


# Columnas que se muestran en las tablas de resultados, en este orden.
columnas_resultado = [
    "fecha",
    "delito",
    "subdelito",
    "victima",
    "subvictima",
    "sexo",
    "edad",
    "nacionalidad",
    "franja_horaria",
    "provincia",
    "canton",
    "tasa_desempleo",
    "economia_predominante",
]

# Nombres legibles para los campos que aparecen en los controles de la interfaz.
nombres_campos = {
    "delito": "Tipo de delito",
    "subdelito": "Subtipo de delito",
    "provincia": "Provincia",
    "canton": "Cantón",
    "victima": "Tipo de víctima",
    "subvictima": "Subtipo de víctima",
    "sexo": "Sexo de la víctima",
    "edad": "Edad de la víctima",
    "nacionalidad": "Nacionalidad de la víctima",
    "periodo_dia": "Periodo del día",
    "dia_semana": "Día de la semana",
    "anio": "Año",
    "economia_predominante": "Economía predominante del cantón",
    "nivel_desempleo": "Nivel de desempleo del cantón",
    "fecha": "Fecha",
    "tasa_desempleo": "Tasa de desempleo (%)",
    "tasa_delitos_anual_1000": "Delitos por año por cada 1000 habitantes",
    "pct_sector_primario": "% ocupados en sector primario",
    "pct_sector_terciario": "% ocupados en sector terciario",
    "relacion_dependencia": "Relación de dependencia económica",
    "hora_inicio": "Hora de inicio de la franja",
    "metodos_anomalia": "Métodos que marcan el mes como anómalo",
}


def nombre_legible(campo):
    # Devuelve el nombre legible si existe; si no, el nombre técnico del campo.
    return nombres_campos.get(campo, campo)


# ---------------------------------------------------------------------------
# Construcción de consultas
# ---------------------------------------------------------------------------

def valor_exacto(campo, valor):
    """
    Arma una condición campo:"valor" para buscar un valor exacto.
    Las comillas son necesarias porque muchos valores tienen espacios ("ROBO DE VEHICULO"); sin
    ellas, Solr interpretaría cada palabra como una condición distinta.
    """
    valor_escapado = str(valor).replace("\\", "\\\\").replace('"', '\\"')
    return campo + ':"' + valor_escapado + '"'


def varios_valores(campo, valores):
    """
    Arma una condición que acepta cualquiera de varios valores, unidos con OR:
    campo:("A" OR "B" OR "C").
    """
    partes = []
    for valor in valores:
        valor_escapado = str(valor).replace("\\", "\\\\").replace('"', '\\"')
        partes.append('"' + valor_escapado + '"')
    return campo + ":(" + " OR ".join(partes) + ")"


def fecha_solr(fecha, fin_del_dia=False):
    # Solr guarda las fechas en formato ISO 8601 con zona UTC: 2024-05-01T00:00:00Z.
    if fin_del_dia:
        return fecha.isoformat() + "T23:59:59Z"
    return fecha.isoformat() + "T00:00:00Z"


# ---------------------------------------------------------------------------
# Ejecución de consultas
# ---------------------------------------------------------------------------

def ejecutar_select(parametros):
    """
    Envía una consulta al endpoint /select de Solr y devuelve la respuesta.
    Si Solr responde con un error, lo muestra en pantalla y devuelve None.
    """
    try:
        return obtener_json(url_core + "/select", parametros)
    except ErrorSolr as error:
        st.error("Solr rechazó la consulta: " + str(error))
    except OSError:
        st.error("No se pudo conectar con Solr. Revise que el contenedor esté encendido (docker compose up -d).")
    return None


def mostrar_consulta(parametros):
    """
    Muestra los parámetros que se enviaron a Solr, para que se pueda ver cómo se construyó la
    consulta. Es útil para explicar cada consulta y para la documentación.
    """
    with st.expander("Ver la consulta enviada a Solr"):
        st.code(json.dumps(parametros, indent=2, ensure_ascii=False), language="json")


def total_encontrados(respuesta):
    return respuesta["response"]["numFound"]


def documentos_a_tabla(respuesta, columnas=None):
    """Convierte la lista de documentos de la respuesta en una tabla de pandas."""
    if columnas is None:
        columnas = columnas_resultado

    filas = []
    for documento in respuesta["response"]["docs"]:
        fila = {}
        for columna in columnas:
            valor = documento.get(columna, "")
            if columna == "fecha" and valor != "":
                valor = valor[:10]
            fila[nombre_legible(columna)] = valor
        filas.append(fila)
    return pd.DataFrame(filas)


def lista_plana_a_tabla(lista_plana, nombre_valor, nombre_conteo="Cantidad"):
    """
    Los facets clásicos de Solr devuelven una lista plana que alterna valor y conteo:
    ["HURTO", 120000, "ROBO", 30000, ...]. Esta función la convierte en una tabla de dos columnas.
    """
    filas = []
    posicion = 0
    while posicion < len(lista_plana):
        filas.append({nombre_valor: lista_plana[posicion], nombre_conteo: lista_plana[posicion + 1]})
        posicion = posicion + 2
    return pd.DataFrame(filas)


@st.cache_data(ttl=3600, show_spinner=False)
def valores_de_campo(campo, limite=200):
    """
    Obtiene los valores distintos de un campo con un field facet, ordenados por frecuencia.
    Se usa para llenar las listas desplegables con los valores reales de los datos.
    st.cache_data guarda el resultado durante una hora para no repetir la consulta en cada clic.
    """
    parametros = {
        "q": "*:*",
        "rows": 0,
        "facet": "true",
        "facet.field": campo,
        "facet.limit": limite,
        "facet.mincount": 1,
    }
    try:
        respuesta = obtener_json(url_core + "/select", parametros)
    except (ErrorSolr, OSError):
        return []

    lista_plana = respuesta["facet_counts"]["facet_fields"][campo]
    valores = []
    posicion = 0
    while posicion < len(lista_plana):
        valores.append(lista_plana[posicion])
        posicion = posicion + 2
    return valores


@st.cache_data(ttl=60, show_spinner=False)
def total_documentos():
    """Cantidad total de documentos indexados, o None si Solr no responde."""
    try:
        respuesta = obtener_json(url_core + "/select", {"q": "*:*", "rows": 0})
        return respuesta["response"]["numFound"]
    except (ErrorSolr, OSError):
        return None
