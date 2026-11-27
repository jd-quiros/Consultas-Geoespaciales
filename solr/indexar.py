"""
Indexa en Solr los documentos generados por el ETL.

Lee etl/salida/datos_solr.jsonl (el archivo que genera el notebook). Si no existe, usa la versión
comprimida etl/salida/datos_solr.jsonl.gz, que es la que se guarda en el repositorio: así se puede
indexar sin volver a ejecutar el ETL.

Uso (desde la raíz del repositorio, con Solr encendido y el schema ya creado):
    python3 solr/indexar.py

Pasos:
1. Borra los documentos que hubiera en el core, para que el índice quede igual al archivo.
2. Lee el archivo línea por línea (cada línea es un documento JSON) y los envía en lotes.
3. Confirma los cambios (commit) y verifica que la cantidad indexada sea igual a la del archivo.
"""

import gzip
import json
import os
import time

from cliente_solr import url_core, enviar_json, obtener_json, verificar_solr

# Ruta del archivo, calculada a partir de la ubicación de este script, para que funcione sin
# importar desde qué carpeta se ejecute.
carpeta_script = os.path.dirname(os.path.abspath(__file__))
ruta_documentos = os.path.join(carpeta_script, "..", "etl", "salida", "datos_solr.jsonl")
ruta_comprimida = ruta_documentos + ".gz"

# Cantidad de documentos por petición. Enviar de uno en uno haría 240 mil peticiones HTTP; enviar
# todos juntos sería una sola petición de 220 MB. Lotes de 5000 (unos 5 MB) son un punto medio.
tamano_lote = 5000


def borrar_documentos():
    # delete con la consulta *:* borra todos los documentos del core.
    # commit = true hace que el borrado se aplique de inmediato.
    enviar_json(url_core + "/update?commit=true", {"delete": {"query": "*:*"}})
    print("Documentos anteriores borrados.")


def enviar_lote(lote):
    # /update recibe una lista JSON de documentos. Sin commit, Solr los recibe pero todavía no los
    # muestra en las búsquedas; se confirma todo al final, que es mucho más rápido que confirmar
    # cada lote.
    enviar_json(url_core + "/update", lote)


def abrir_documentos():
    """
    Abre el archivo de documentos como texto. gzip.open lee el archivo comprimido y lo descomprime
    mientras se lee, sin crear una copia descomprimida en el disco.
    """
    if os.path.exists(ruta_documentos):
        print("Leyendo", os.path.normpath(ruta_documentos))
        return open(ruta_documentos, encoding="utf-8")
    if os.path.exists(ruta_comprimida):
        print("Leyendo", os.path.normpath(ruta_comprimida))
        return gzip.open(ruta_comprimida, mode="rt", encoding="utf-8")
    raise SystemExit(
        "No se encontró " + os.path.normpath(ruta_documentos) + " ni su versión comprimida (.gz).\n"
        "Se generan al ejecutar el notebook etl/ETL_Crimen_Economia.ipynb."
    )


def indexar_archivo():

    total_enviados = 0
    lote = []
    inicio = time.time()

    with abrir_documentos() as archivo:
        for linea in archivo:
            linea = linea.strip()
            if linea == "":
                continue
            lote.append(json.loads(linea))

            if len(lote) == tamano_lote:
                enviar_lote(lote)
                total_enviados = total_enviados + len(lote)
                lote = []
                segundos = round(time.time() - inicio, 1)
                print("  Enviados:", total_enviados, "documentos (" + str(segundos) + " s)")

    # El último lote puede tener menos de tamano_lote documentos.
    if len(lote) > 0:
        enviar_lote(lote)
        total_enviados = total_enviados + len(lote)
        print("  Enviados:", total_enviados, "documentos")

    # commit: hace visibles en las búsquedas todos los documentos enviados.
    print("Confirmando cambios (commit)...")
    enviar_json(url_core + "/update?commit=true", {"commit": {}})

    segundos = round(time.time() - inicio, 1)
    print("Indexación terminada en", segundos, "segundos.")
    return total_enviados


def verificar_indice(total_esperado):
    # rows = 0: no se piden documentos, solo el total (numFound).
    respuesta = obtener_json(url_core + "/select", {"q": "*:*", "rows": 0})
    total_indexado = respuesta["response"]["numFound"]

    print("Documentos en el archivo:", total_esperado)
    print("Documentos en Solr:", total_indexado)
    if total_indexado != total_esperado:
        raise SystemExit("La cantidad indexada no coincide con la del archivo.")

    # Prueba rápida de la búsqueda geoespacial: delitos a 5 km o menos del centro de San José.
    respuesta = obtener_json(
        url_core + "/select",
        {
            "q": "*:*",
            "fq": "{!geofilt sfield=ubicacion pt=9.9333,-84.0833 d=5}",
            "rows": 0,
        },
    )
    print("Prueba geoespacial (5 km del centro de San José):", respuesta["response"]["numFound"], "delitos")


def main():
    verificar_solr()
    borrar_documentos()
    total = indexar_archivo()
    verificar_indice(total)


if __name__ == "__main__":
    main()
