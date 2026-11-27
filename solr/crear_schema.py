"""
Crea el schema del core "crimen" en Solr: los tipos de campo, los campos y las copias de campos.

Uso (desde la raíz del repositorio, con Solr encendido):
    python3 solr/crear_schema.py

El script se puede ejecutar varias veces: si un campo ya existe, lo reemplaza con la definición
de este archivo en lugar de fallar. Así el schema siempre queda igual a lo que dice el código.
"""

from cliente_solr import url_core, enviar_json, obtener_json, verificar_solr


# ---------------------------------------------------------------------------
# Tipo de campo espacial
# ---------------------------------------------------------------------------
# RptWithGeometrySpatialField es una variante de SpatialRecursivePrefixTreeFieldType (RPT).
# RPT divide el mapa en una cuadrícula de celdas cada vez más pequeñas y anota en qué celdas cae cada
# punto; así responde consultas por radio o por polígono sin revisar los documentos uno por uno.
# El problema es que RPT solo es APROXIMADO: una celda que toca el borde del polígono cuenta como
# "adentro", así que se cuelan puntos que están un poco afuera. Las pruebas lo detectaron (ver
# pruebas/resultados_pruebas_rpt_aproximado.md): con un radio de 5 km aparecían puntos a 5,14 km.
# RptWithGeometrySpatialField usa la misma cuadrícula para encontrar los candidatos rápido, y después
# verifica cada candidato contra la geometría exacta, por lo que el resultado es exacto.
# - spatialContextFactory = JTS: usa la librería JTS, necesaria para polígonos arbitrarios.
# - geo = true: las coordenadas son latitud y longitud sobre la Tierra (no un plano).
# - distanceUnits = kilometers: los radios de las búsquedas se expresan en kilómetros.
tipo_espacial = {
    "name": "location_jts",
    "class": "solr.RptWithGeometrySpatialField",
    "spatialContextFactory": "JTS",
    "geo": "true",
    "autoIndex": "true",
    "validationRule": "repairBuffer0",
    "distanceUnits": "kilometers",
}


# ---------------------------------------------------------------------------
# Campos de los documentos
# ---------------------------------------------------------------------------
# Cada tupla es (nombre del campo, tipo de Solr). Los tipos vienen definidos en el schema por
# defecto de Solr:
# - string: texto exacto, sin dividir en palabras. Se usa para categorías, porque los facets y los
#   filtros necesitan comparar el valor completo ("ROBO DE VEHICULO" y no "robo", "de", "vehiculo").
# - pint / pdouble: números enteros y decimales. Permiten rangos, ordenamiento y estadísticas.
# - pdate: fecha y hora en formato ISO 8601. Permite rangos de fechas y facets por periodo.
# - boolean: verdadero o falso.
# El campo "id" no aparece porque ya existe en el schema por defecto como llave única.
campos = [
    # Datos del delito
    ("delito", "string"),
    ("subdelito", "string"),
    ("fecha", "pdate"),
    ("anio", "pint"),
    ("mes", "pint"),
    ("periodo", "string"),
    ("dia_semana", "string"),
    ("es_fin_de_semana", "boolean"),
    ("franja_horaria", "string"),
    ("hora_inicio", "pint"),
    ("periodo_dia", "string"),
    # Datos de la víctima
    ("victima", "string"),
    ("subvictima", "string"),
    ("edad", "string"),
    ("sexo", "string"),
    ("nacionalidad", "string"),
    ("sexo_imputado", "boolean"),
    ("edad_imputada", "boolean"),
    # Ubicación
    ("provincia", "string"),
    ("canton", "string"),
    ("canton_censo", "string"),
    ("latitud", "pdouble"),
    ("longitud", "pdouble"),
    ("ubicacion", "location_jts"),
    # Indicadores económicos del cantón (Censo 2011)
    ("poblacion_15_mas", "pint"),
    ("tasa_participacion", "pdouble"),
    ("tasa_ocupacion", "pdouble"),
    ("tasa_desempleo", "pdouble"),
    ("pct_inactiva", "pdouble"),
    ("relacion_dependencia", "pdouble"),
    ("pct_sector_primario", "pdouble"),
    ("pct_sector_secundario", "pdouble"),
    ("pct_sector_terciario", "pdouble"),
    ("economia_predominante", "string"),
    ("nivel_desempleo", "string"),
    # Resultados del análisis
    ("tasa_delitos_anual_1000", "pdouble"),
    ("metodos_anomalia", "pint"),
    ("mes_anomalo", "boolean"),
]

# ---------------------------------------------------------------------------
# Campo de búsqueda de texto libre
# ---------------------------------------------------------------------------
# Los campos string solo encuentran el valor exacto. Para poder buscar palabras sueltas (por ejemplo
# "taxista" o "robos"), se crea el campo "texto" de tipo text_es: Solr lo divide en palabras, lo pasa
# a minúsculas y aplica reglas del español (como reducir "robos" a su raíz).
# Las copias de campo (copyField) hacen que, al indexar, el contenido de varios campos se copie
# automáticamente en "texto". Como "texto" solo sirve para buscar, no se guarda (stored = false).
campo_texto = {
    "name": "texto",
    "type": "text_es",
    "indexed": True,
    "stored": False,
    "multiValued": True,
}

campos_copiados_a_texto = [
    "delito",
    "subdelito",
    "victima",
    "subvictima",
    "nacionalidad",
    "provincia",
    "canton",
]


def desactivar_campos_automaticos():
    # Por defecto Solr funciona en modo "schemaless": si llega un campo que no existe, adivina su
    # tipo y lo crea. Eso puede producir tipos incorrectos, así que se desactiva: los campos se
    # definen solo en este script.
    enviar_json(url_core + "/config", {"set-user-property": {"update.autoCreateFields": "false"}})
    print("Creación automática de campos desactivada.")


def crear_tipo_espacial():
    existente = obtener_json(url_core + "/schema/fieldtypes/" + tipo_espacial["name"], permitir_no_encontrado=True)
    if existente is None:
        enviar_json(url_core + "/schema", {"add-field-type": tipo_espacial})
        print("Tipo creado:", tipo_espacial["name"])
    else:
        enviar_json(url_core + "/schema", {"replace-field-type": tipo_espacial})
        print("Tipo reemplazado:", tipo_espacial["name"])


def crear_campos():
    # Se separan los campos nuevos de los que ya existen, porque Solr usa comandos distintos:
    # add-field para crear y replace-field para actualizar.
    campos_nuevos = []
    campos_existentes = []

    for nombre, tipo in campos:
        definicion = {
            "name": nombre,
            "type": tipo,
            "indexed": True,
            "stored": True,
            "multiValued": False,
        }
        existente = obtener_json(url_core + "/schema/fields/" + nombre, permitir_no_encontrado=True)
        if existente is None:
            campos_nuevos.append(definicion)
        else:
            campos_existentes.append(definicion)

    existente_texto = obtener_json(url_core + "/schema/fields/" + campo_texto["name"], permitir_no_encontrado=True)
    if existente_texto is None:
        campos_nuevos.append(campo_texto)
    else:
        campos_existentes.append(campo_texto)

    # La API de schema acepta una lista de campos en un solo comando.
    comandos = {}
    if len(campos_nuevos) > 0:
        comandos["add-field"] = campos_nuevos
    if len(campos_existentes) > 0:
        comandos["replace-field"] = campos_existentes

    enviar_json(url_core + "/schema", comandos)
    print("Campos creados:", len(campos_nuevos), "| campos reemplazados:", len(campos_existentes))


def crear_copias_a_texto():
    # Se consultan las copias que ya existen hacia "texto", para no duplicarlas.
    respuesta = obtener_json(url_core + "/schema/copyfields", {"dest.fl": campo_texto["name"]})
    origenes_existentes = []
    for copia in respuesta.get("copyFields", []):
        origenes_existentes.append(copia["source"])

    copias_nuevas = []
    for origen in campos_copiados_a_texto:
        if origen not in origenes_existentes:
            copias_nuevas.append({"source": origen, "dest": campo_texto["name"]})

    if len(copias_nuevas) > 0:
        enviar_json(url_core + "/schema", {"add-copy-field": copias_nuevas})
    print("Copias de campo hacia 'texto' agregadas:", len(copias_nuevas))


def verificar_schema():
    # Se vuelve a leer el schema desde Solr y se confirma que cada campo tenga el tipo esperado.
    respuesta = obtener_json(url_core + "/schema/fields")
    tipos_en_solr = {}
    for campo in respuesta["fields"]:
        tipos_en_solr[campo["name"]] = campo["type"]

    errores = 0
    for nombre, tipo in campos:
        if tipos_en_solr.get(nombre) != tipo:
            print("  ERROR:", nombre, "esperaba", tipo, "y Solr tiene", tipos_en_solr.get(nombre))
            errores = errores + 1

    if errores == 0:
        print("Verificación correcta:", len(campos) + 1, "campos definidos con el tipo esperado.")
    else:
        raise SystemExit("La verificación encontró " + str(errores) + " errores.")


def main():
    verificar_solr()
    desactivar_campos_automaticos()
    crear_tipo_espacial()
    crear_campos()
    crear_copias_a_texto()
    verificar_schema()


if __name__ == "__main__":
    main()
