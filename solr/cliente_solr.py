"""
Funciones para comunicarse con Apache Solr por HTTP.

Solr no se consulta con un lenguaje como SQL: todo se hace con peticiones HTTP a URLs del core.
- /schema   -> definir campos y tipos (equivalente a CREATE TABLE)
- /update   -> agregar o borrar documentos (equivalente a INSERT y DELETE)
- /select   -> consultar (equivalente a SELECT)

Este módulo usa solo la biblioteca estándar de Python (urllib y json), así que no hace falta
instalar nada. Lo usan los scripts de esta carpeta y la aplicación.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

url_solr = "http://localhost:8983/solr"
nombre_core = "crimen"
url_core = url_solr + "/" + nombre_core


class ErrorSolr(Exception):
    """Error devuelto por Solr, con el mensaje que Solr explica en su respuesta."""
    pass


def leer_respuesta(respuesta):
    # Solr responde en JSON; se convierte a diccionario de Python.
    contenido = respuesta.read().decode("utf-8")
    if contenido == "":
        return {}
    return json.loads(contenido)


def explicar_error_http(error):
    # Cuando Solr rechaza una petición, el motivo viene en el cuerpo de la respuesta.
    # Se extrae para mostrar un mensaje útil en lugar de solo "HTTP Error 400".
    cuerpo = error.read().decode("utf-8", errors="replace")
    try:
        datos = json.loads(cuerpo)
        if "error" in datos and "msg" in datos["error"]:
            return datos["error"]["msg"]
        if "errors" in datos:
            return json.dumps(datos["errors"], ensure_ascii=False)
    except json.JSONDecodeError:
        pass
    return cuerpo[:500]


def obtener_json(url, parametros=None, permitir_no_encontrado=False):
    """
    Hace una petición GET y devuelve la respuesta como diccionario.
    Si permitir_no_encontrado es True y Solr responde 404, devuelve None en lugar de fallar
    (sirve para preguntar si un campo o un tipo ya existe).
    """
    if parametros is not None:
        # urlencode arma la parte "?q=...&rows=..." escapando los caracteres especiales.
        # doseq=True permite repetir un parámetro (por ejemplo, varios fq).
        url = url + "?" + urllib.parse.urlencode(parametros, doseq=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as respuesta:
            return leer_respuesta(respuesta)
    except urllib.error.HTTPError as error:
        if permitir_no_encontrado and error.code == 404:
            return None
        raise ErrorSolr(explicar_error_http(error)) from None


def enviar_json(url, datos, tiempo_maximo=300):
    """Hace una petición POST con un cuerpo JSON y devuelve la respuesta como diccionario."""
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    peticion = urllib.request.Request(
        url,
        data=cuerpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=tiempo_maximo) as respuesta:
            return leer_respuesta(respuesta)
    except urllib.error.HTTPError as error:
        raise ErrorSolr(explicar_error_http(error)) from None


def verificar_solr():
    """
    Revisa que Solr esté encendido y que exista el core.
    Si algo falla, termina con un mensaje que dice qué hacer.
    """
    try:
        estado = obtener_json(url_solr + "/admin/cores", {"action": "STATUS", "core": nombre_core})
    except urllib.error.URLError:
        raise SystemExit(
            "No se pudo conectar con Solr en " + url_solr + ".\n"
            "Revise que Docker (OrbStack) esté abierto y ejecute: docker compose up -d"
        )

    # Si el core no existe, Solr devuelve su estado como un diccionario vacío.
    if estado.get("status", {}).get(nombre_core, {}) == {}:
        raise SystemExit(
            "Solr está encendido, pero no existe el core '" + nombre_core + "'.\n"
            "El core se crea al levantar el contenedor con: docker compose up -d"
        )
