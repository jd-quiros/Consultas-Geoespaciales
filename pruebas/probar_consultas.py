"""
Pruebas de las consultas contra el Solr real.

Cada prueba ejecuta una o más consultas y verifica una propiedad que se debe cumplir si la
indexación y las consultas funcionan bien. Por ejemplo: la suma de un facet debe ser igual al total
de documentos, o todos los puntos que devuelve una búsqueda por radio deben estar dentro del radio.

Uso (desde la raíz del repositorio, con Solr encendido y los datos indexados):
    python3 pruebas/probar_consultas.py

Además de imprimir los resultados, los guarda en pruebas/resultados_pruebas.md para la documentación.
"""

import datetime
import gzip
import json
import math
import os
import sys

carpeta_script = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(carpeta_script, "..", "solr"))

from cliente_solr import url_core, enviar_json, obtener_json, verificar_solr  # noqa: E402

ruta_resultados = os.path.join(carpeta_script, "resultados_pruebas.md")
ruta_cantones = os.path.join(carpeta_script, "..", "etl", "datos", "cantones.geojson")
ruta_documentos = os.path.join(carpeta_script, "..", "etl", "salida", "datos_solr.jsonl")

resultados = []


def registrar(nombre, descripcion, obtenido, paso):
    """Guarda el resultado de una prueba y lo imprime."""
    estado = "PASA" if paso else "FALLA"
    resultados.append((nombre, descripcion, obtenido, estado))
    print("[" + estado + "] " + nombre + ": " + obtenido)


def contar(consulta, filtros=None):
    """Cantidad de documentos que cumplen una consulta (numFound), sin pedir documentos (rows = 0)."""
    parametros = {"q": consulta, "rows": 0}
    if filtros is not None:
        parametros["fq"] = filtros
    return obtener_json(url_core + "/select", parametros)["response"]["numFound"]


def conteos_facet(campo, filtros=None):
    """Devuelve un diccionario valor -> cantidad usando un field facet."""
    parametros = {"q": "*:*", "rows": 0, "facet": "true", "facet.field": campo, "facet.limit": -1, "facet.mincount": 1}
    if filtros is not None:
        parametros["fq"] = filtros
    lista_plana = obtener_json(url_core + "/select", parametros)["facet_counts"]["facet_fields"][campo]
    conteos = {}
    posicion = 0
    while posicion < len(lista_plana):
        conteos[lista_plana[posicion]] = lista_plana[posicion + 1]
        posicion = posicion + 2
    return conteos


def contar_con_post(filtros):
    """
    Igual que contar(), pero envía la consulta con el JSON Request API (POST a /query).
    Se usa para los polígonos reales de los cantones, que tienen miles de vértices y no caben en
    una URL de una petición GET.
    """
    respuesta = enviar_json(url_core + "/query", {"query": "*:*", "filter": filtros, "limit": 0})
    return respuesta["response"]["numFound"]


def distancia_km(latitud_1, longitud_1, latitud_2, longitud_2):
    """Distancia entre dos puntos sobre la Tierra con la fórmula de Haversine."""
    radio_tierra = 6371.0088
    fi_1 = math.radians(latitud_1)
    fi_2 = math.radians(latitud_2)
    delta_fi = math.radians(latitud_2 - latitud_1)
    delta_lambda = math.radians(longitud_2 - longitud_1)
    a = math.sin(delta_fi / 2) ** 2 + math.cos(fi_1) * math.cos(fi_2) * math.sin(delta_lambda / 2) ** 2
    return 2 * radio_tierra * math.asin(math.sqrt(a))


def distancia_al_borde_m(latitud, longitud, vertices):
    """
    Distancia aproximada en metros entre un punto y el borde de un polígono.
    Para distancias tan cortas, se puede tratar la zona como un plano: los grados de latitud se
    convierten a metros multiplicando por 111 320, y los de longitud además por el coseno de la latitud.
    Se calcula la distancia del punto a cada lado del polígono y se toma la menor.
    """
    metros_por_grado = 111320.0
    escala_longitud = math.cos(math.radians(latitud))
    menor = None
    posicion = 0
    while posicion < len(vertices) - 1:
        x1 = (vertices[posicion][0] - longitud) * metros_por_grado * escala_longitud
        y1 = (vertices[posicion][1] - latitud) * metros_por_grado
        x2 = (vertices[posicion + 1][0] - longitud) * metros_por_grado * escala_longitud
        y2 = (vertices[posicion + 1][1] - latitud) * metros_por_grado
        dx = x2 - x1
        dy = y2 - y1
        largo_cuadrado = dx * dx + dy * dy
        # t es la posición, sobre el lado, del punto más cercano al origen (que es el punto evaluado).
        t = 0.0
        if largo_cuadrado > 0:
            t = -(x1 * dx + y1 * dy) / largo_cuadrado
            if t < 0:
                t = 0.0
            if t > 1:
                t = 1.0
        cercano_x = x1 + t * dx
        cercano_y = y1 + t * dy
        distancia = math.sqrt(cercano_x * cercano_x + cercano_y * cercano_y)
        if menor is None or distancia < menor:
            menor = distancia
        posicion = posicion + 1
    return menor


def formato(numero):
    return f"{numero:,}".replace(",", " ")


# ---------------------------------------------------------------------------
# Pruebas de indexación
# ---------------------------------------------------------------------------
def prueba_total_indexado():
    if os.path.exists(ruta_documentos):
        archivo = open(ruta_documentos, encoding="utf-8")
    else:
        archivo = gzip.open(ruta_documentos + ".gz", mode="rt", encoding="utf-8")
    lineas = 0
    with archivo:
        for linea in archivo:
            if linea.strip() != "":
                lineas = lineas + 1
    total = contar("*:*")
    registrar(
        "Indexación completa",
        "La cantidad de documentos en Solr es igual a la cantidad de líneas del archivo generado por el ETL.",
        "archivo: " + formato(lineas) + ", Solr: " + formato(total),
        lineas == total,
    )


def prueba_campos_espaciales():
    # Se revisa el campo latitud porque el campo espacial no admite la consulta de rango [* TO *].
    # Los tres campos (latitud, longitud y ubicacion) se generan juntos en el ETL.
    sin_ubicacion = contar("*:* -latitud:[* TO *]")
    registrar(
        "Todos los documentos tienen coordenadas",
        "Ningún documento queda sin coordenadas.",
        "documentos sin ubicación: " + formato(sin_ubicacion),
        sin_ubicacion == 0,
    )


# ---------------------------------------------------------------------------
# Pruebas de consultas convencionales
# ---------------------------------------------------------------------------
def prueba_and_con_q_y_fq():
    con_q = contar('delito:"ASALTO" AND provincia:"LIMON"')
    con_fq = contar("*:*", ['delito:"ASALTO"', 'provincia:"LIMON"'])
    registrar(
        "Operador AND frente a filtros fq",
        "Unir dos condiciones con AND en q da la misma cantidad que enviarlas como dos fq.",
        "q con AND: " + formato(con_q) + ", dos fq: " + formato(con_fq),
        con_q == con_fq and con_q > 0,
    )


def prueba_or():
    garabito = contar('canton:"GARABITO"')
    quepos = contar('canton:"QUEPOS"')
    ambos = contar('canton:("GARABITO" OR "QUEPOS")')
    registrar(
        "Operador OR",
        "Como un delito pertenece a un solo cantón, el OR de dos cantones suma los delitos de ambos.",
        "Garabito: " + formato(garabito) + " + Quepos: " + formato(quepos) + " = OR: " + formato(ambos),
        garabito + quepos == ambos,
    )


def prueba_not():
    homicidios = contar('delito:"HOMICIDIO"')
    costarricenses = contar('delito:"HOMICIDIO" AND nacionalidad:"COSTA RICA"')
    no_costarricenses = contar('delito:"HOMICIDIO" AND NOT nacionalidad:"COSTA RICA"')
    registrar(
        "Operador NOT",
        "Los registros con una condición más los registros con su negación dan el total.",
        "COSTA RICA: " + formato(costarricenses) + " + NOT COSTA RICA: " + formato(no_costarricenses)
        + " = total: " + formato(homicidios),
        costarricenses + no_costarricenses == homicidios,
    )


def prueba_texto_libre():
    por_texto = contar("texto:(taxista)")
    por_campo = contar('subvictima:"TAXISTA"')
    registrar(
        "Búsqueda de texto libre",
        "Buscar la palabra 'taxista' en el campo de texto encuentra al menos los registros cuya subvíctima es TAXISTA.",
        "texto:taxista: " + formato(por_texto) + ", subvictima TAXISTA: " + formato(por_campo),
        por_texto >= por_campo and por_campo > 0,
    )


def prueba_rango_fechas():
    anio_2020 = contar("fecha:[2020-01-01T00:00:00Z TO 2020-12-31T23:59:59Z]")
    por_campo_anio = contar("anio:2020")
    registrar(
        "Rango temporal",
        "El rango de fechas de 2020 devuelve lo mismo que el campo anio = 2020.",
        "rango de fechas: " + formato(anio_2020) + ", anio:2020: " + formato(por_campo_anio),
        anio_2020 == por_campo_anio and anio_2020 > 0,
    )


def prueba_rango_numerico():
    alto = contar("tasa_desempleo:[4 TO *]")
    bajo = contar("tasa_desempleo:[* TO 4}")
    total = contar("*:*")
    registrar(
        "Rango numérico",
        "Los rangos [4 TO *] y [* TO 4} se complementan: juntos suman el total (la llave } excluye el 4).",
        "desempleo >= 4: " + formato(alto) + " + desempleo < 4: " + formato(bajo) + " = " + formato(total),
        alto + bajo == total and alto > 0 and bajo > 0,
    )


def prueba_ordenamiento():
    respuesta = obtener_json(url_core + "/select", {
        "q": 'delito:"ROBO"',
        "sort": "tasa_desempleo desc, fecha desc",
        "fl": "tasa_desempleo,fecha",
        "rows": 200,
    })
    documentos = respuesta["response"]["docs"]
    ordenado = True
    posicion = 1
    while posicion < len(documentos):
        anterior = documentos[posicion - 1]
        actual = documentos[posicion]
        if actual["tasa_desempleo"] > anterior["tasa_desempleo"]:
            ordenado = False
        if actual["tasa_desempleo"] == anterior["tasa_desempleo"] and actual["fecha"] > anterior["fecha"]:
            ordenado = False
        posicion = posicion + 1
    registrar(
        "Ordenamiento por dos atributos",
        "En los primeros 200 resultados, la tasa de desempleo nunca sube y, cuando empata, la fecha nunca sube.",
        "documentos revisados: " + str(len(documentos)),
        ordenado and len(documentos) > 0,
    )


# ---------------------------------------------------------------------------
# Pruebas de facets
# ---------------------------------------------------------------------------
def prueba_field_facet():
    conteos = conteos_facet("delito")
    suma = 0
    for valor in conteos:
        suma = suma + conteos[valor]
    total = contar("*:*")
    registrar(
        "Field facet",
        "La suma de los conteos del facet por tipo de delito es igual al total de documentos.",
        "suma del facet: " + formato(suma) + ", total: " + formato(total),
        suma == total,
    )


def prueba_range_facet():
    respuesta = obtener_json(url_core + "/select", {
        "q": "*:*",
        "rows": 0,
        "facet": "true",
        "facet.range": "fecha",
        "facet.range.start": "2019-01-01T00:00:00Z",
        "facet.range.end": "2027-01-01T00:00:00Z",
        "facet.range.gap": "+1YEAR",
    })
    lista_plana = respuesta["facet_counts"]["facet_ranges"]["fecha"]["counts"]
    suma = 0
    posicion = 1
    while posicion < len(lista_plana):
        suma = suma + lista_plana[posicion]
        posicion = posicion + 2
    total = respuesta["response"]["numFound"]
    registrar(
        "Range facet",
        "La suma de los intervalos anuales de 2019 a 2026 es igual al total de documentos.",
        "suma de los intervalos: " + formato(suma) + ", total: " + formato(total),
        suma == total,
    )


def prueba_facet_anidado():
    facet = {
        "economia": {
            "type": "terms",
            "field": "economia_predominante",
            "facet": {"delitos": {"type": "terms", "field": "delito", "limit": -1}},
        }
    }
    respuesta = obtener_json(url_core + "/select", {"q": "*:*", "rows": 0, "json.facet": json.dumps(facet)})
    correcto = True
    grupos = 0
    for grupo in respuesta["facets"]["economia"]["buckets"]:
        suma_interna = 0
        for subgrupo in grupo["delitos"]["buckets"]:
            suma_interna = suma_interna + subgrupo["count"]
        if suma_interna != grupo["count"]:
            correcto = False
        grupos = grupos + 1
    registrar(
        "Facet anidado",
        "En cada tipo de economía, la suma de los subgrupos por delito es igual al conteo del grupo.",
        "grupos revisados: " + str(grupos),
        correcto and grupos > 0,
    )


def prueba_facet_estadistico():
    facet = {
        "cantones": {
            "type": "terms",
            "field": "canton_censo",
            "limit": -1,
            "facet": {"minimo": "min(tasa_desempleo)", "maximo": "max(tasa_desempleo)"},
        }
    }
    respuesta = obtener_json(url_core + "/select", {"q": "*:*", "rows": 0, "json.facet": json.dumps(facet)})
    inconsistentes = 0
    cantones = 0
    for grupo in respuesta["facets"]["cantones"]["buckets"]:
        if abs(grupo["minimo"] - grupo["maximo"]) > 1e-9:
            inconsistentes = inconsistentes + 1
        cantones = cantones + 1
    registrar(
        "Facet con funciones estadísticas",
        "La tasa de desempleo es un dato del cantón, así que en cada cantón del censo el mínimo y el máximo coinciden.",
        "cantones revisados: " + str(cantones) + ", cantones con mínimo distinto del máximo: " + str(inconsistentes),
        inconsistentes == 0 and cantones == 81,
    )


# ---------------------------------------------------------------------------
# Pruebas geoespaciales
# ---------------------------------------------------------------------------
def prueba_proximidad():
    centro_latitud = 9.9333
    centro_longitud = -84.0833
    radio = 5
    filtro = "{!geofilt sfield=ubicacion pt=" + str(centro_latitud) + "," + str(centro_longitud) + " d=" + str(radio) + "}"
    respuesta = obtener_json(url_core + "/select", {"q": "*:*", "fq": filtro, "fl": "latitud,longitud", "rows": 3000})
    total = respuesta["response"]["numFound"]
    maxima = 0.0
    for documento in respuesta["response"]["docs"]:
        distancia = distancia_km(centro_latitud, centro_longitud, documento["latitud"], documento["longitud"])
        if distancia > maxima:
            maxima = distancia
    registrar(
        "Proximidad: puntos dentro del radio",
        "Todos los puntos devueltos por una búsqueda de 5 km alrededor del centro de San José están a 5 km o menos "
        "(distancia calculada aparte con la fórmula de Haversine).",
        "encontrados: " + formato(total) + ", distancia máxima revisada: " + str(round(maxima, 3)) + " km",
        total > 0 and maxima <= radio + 0.01,
    )

    mayor = contar("*:*", ["{!geofilt sfield=ubicacion pt=" + str(centro_latitud) + "," + str(centro_longitud) + " d=10}"])
    registrar(
        "Proximidad: radio mayor contiene al menor",
        "Un radio de 10 km encuentra al menos los mismos delitos que uno de 5 km.",
        "5 km: " + formato(total) + ", 10 km: " + formato(mayor),
        mayor >= total,
    )


def prueba_rectangulo():
    longitud_minima = -84.15
    longitud_maxima = -84.0
    latitud_minima = 9.88
    latitud_maxima = 9.98
    wkt = (
        "POLYGON((" + str(longitud_minima) + " " + str(latitud_minima) + ", "
        + str(longitud_maxima) + " " + str(latitud_minima) + ", "
        + str(longitud_maxima) + " " + str(latitud_maxima) + ", "
        + str(longitud_minima) + " " + str(latitud_maxima) + ", "
        + str(longitud_minima) + " " + str(latitud_minima) + "))"
    )
    respuesta = obtener_json(url_core + "/select", {
        "q": "*:*",
        "fq": "{!field f=ubicacion}Intersects(" + wkt + ")",
        "fl": "latitud,longitud",
        "rows": 5000,
    })
    fuera = 0
    for documento in respuesta["response"]["docs"]:
        if not (longitud_minima <= documento["longitud"] <= longitud_maxima and latitud_minima <= documento["latitud"] <= latitud_maxima):
            fuera = fuera + 1
    registrar(
        "Polígono: puntos dentro del área",
        "Ninguno de los puntos devueltos por un polígono rectangular sobre San José queda fuera del rectángulo.",
        "encontrados: " + formato(respuesta["response"]["numFound"]) + ", revisados: "
        + str(len(respuesta["response"]["docs"])) + ", fuera del área: " + str(fuera),
        fuera == 0 and len(respuesta["response"]["docs"]) > 0,
    )


def prueba_poligono_de_canton(nombre_geojson, nombre_canton):
    """
    Usa como consulta el polígono real del cantón (del GeoJSON). Como las coordenadas se generaron
    dentro de ese mismo polígono, la consulta debe recuperar todos los delitos del cantón.
    Puede traer unos pocos de cantones vecinos, porque Solr aproxima el polígono con su cuadrícula
    y algunos puntos cercanos al borde caen en celdas compartidas.
    """
    with open(ruta_cantones, encoding="utf-8") as archivo:
        geojson = json.load(archivo)

    vertices = None
    for feature in geojson["features"]:
        if feature["properties"]["shapeName"] == nombre_geojson and feature["geometry"]["type"] == "Polygon":
            vertices = feature["geometry"]["coordinates"][0]
    if vertices is None:
        print("No se encontró el polígono de", nombre_geojson)
        return

    puntos = []
    for vertice in vertices:
        puntos.append(str(vertice[0]) + " " + str(vertice[1]))
    wkt = "POLYGON((" + ", ".join(puntos) + "))"
    filtro = "{!field f=ubicacion}Intersects(" + wkt + ")"

    delitos_canton = contar('canton:"' + nombre_canton + '"')
    dentro_poligono = contar_con_post([filtro])
    del_canton_en_poligono = contar_con_post([filtro, 'canton:"' + nombre_canton + '"'])
    vecinos = dentro_poligono - del_canton_en_poligono
    porcentaje_vecinos = 0.0
    if dentro_poligono > 0:
        porcentaje_vecinos = vecinos / dentro_poligono * 100

    # Delitos del cantón que la consulta NO recuperó. La negación se escribe con _query_ y el polígono
    # se pasa como parámetro aparte (v=$area), para no tener que escapar el texto del WKT.
    # Las coordenadas se exportaron redondeadas a 6 decimales (unos 5 cm), así que un punto generado
    # justo sobre el borde puede quedar a centímetros del lado de afuera. Se mide su distancia al borde.
    respuesta_faltantes = enviar_json(url_core + "/query", {
        "query": "*:*",
        "filter": ['canton:"' + nombre_canton + '"', '*:* -_query_:"{!field f=ubicacion v=$area}"'],
        "fields": "latitud,longitud",
        "limit": 100,
        "params": {"area": "Intersects(" + wkt + ")"},
    })
    faltantes = respuesta_faltantes["response"]["numFound"]
    distancia_maxima = 0.0
    for documento in respuesta_faltantes["response"]["docs"]:
        distancia = distancia_al_borde_m(documento["latitud"], documento["longitud"], vertices)
        if distancia > distancia_maxima:
            distancia_maxima = distancia

    texto = (
        "delitos del cantón: " + formato(delitos_canton) + ", recuperados: " + formato(del_canton_en_poligono)
        + ", de cantones vecinos: " + formato(vecinos) + " (" + str(round(porcentaje_vecinos, 2)) + " %)"
    )
    if faltantes > 0:
        texto = (
            texto + ", no recuperados: " + str(faltantes) + ", todos a "
            + str(round(distancia_maxima, 3)) + " m o menos del borde (efecto del redondeo de coordenadas)"
        )

    # La prueba pasa si no entran puntos de cantones vecinos y si los puntos no recuperados, si los
    # hay, están a menos de 10 cm del borde: es decir, solo los explica el redondeo a 6 decimales.
    registrar(
        "Polígono real del cantón " + nombre_geojson,
        "La consulta con el polígono del cantón (" + str(len(vertices)) + " vértices) recupera sus delitos y no "
        "incluye delitos de cantones vecinos.",
        texto,
        vecinos == 0 and faltantes < 100 and distancia_maxima < 0.1,
    )


def guardar_resultados():
    pasan = 0
    for resultado in resultados:
        if resultado[3] == "PASA":
            pasan = pasan + 1

    lineas = [
        "# Resultados de las pruebas de consultas",
        "",
        "Ejecutadas con `python3 pruebas/probar_consultas.py` el " + datetime.date.today().isoformat()
        + " contra el core `crimen` de Solr.",
        "",
        "**Resultado: " + str(pasan) + " de " + str(len(resultados)) + " pruebas pasan.**",
        "",
        "| # | Prueba | Qué verifica | Resultado obtenido | Estado |",
        "|---|---|---|---|---|",
    ]
    numero = 1
    for nombre, descripcion, obtenido, estado in resultados:
        lineas.append("| " + str(numero) + " | " + nombre + " | " + descripcion + " | " + obtenido + " | " + estado + " |")
        numero = numero + 1

    with open(ruta_resultados, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas) + "\n")
    print()
    print("Resultado:", pasan, "de", len(resultados), "pruebas pasan.")
    print("Guardado en", os.path.normpath(ruta_resultados))


def main():
    verificar_solr()
    prueba_total_indexado()
    prueba_campos_espaciales()
    prueba_and_con_q_y_fq()
    prueba_or()
    prueba_not()
    prueba_texto_libre()
    prueba_rango_fechas()
    prueba_rango_numerico()
    prueba_ordenamiento()
    prueba_field_facet()
    prueba_range_facet()
    prueba_facet_anidado()
    prueba_facet_estadistico()
    prueba_proximidad()
    prueba_rectangulo()
    prueba_poligono_de_canton("Montes de Oca", "MONTES DE OCA")
    prueba_poligono_de_canton("San Pablo", "SAN PABLO")
    prueba_poligono_de_canton("San Jose", "SAN JOSE")
    guardar_resultados()


if __name__ == "__main__":
    main()
