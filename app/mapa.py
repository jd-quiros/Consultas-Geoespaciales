"""
Funciones para los mapas interactivos (Folium) y para convertir los polígonos dibujados por el
usuario al formato que entiende Solr.

Folium genera mapas de Leaflet (una biblioteca de mapas web) desde Python, y streamlit-folium los
muestra dentro de Streamlit y devuelve lo que el usuario hace en el mapa (clics y figuras dibujadas).
"""

import folium
from folium.plugins import Draw, FastMarkerCluster

centro_costa_rica = [9.75, -84.1]

# Color de cada tipo de delito en los mapas.
colores_delito = {
    "ASALTO": "#d62728",
    "HURTO": "#1f77b4",
    "ROBO": "#ff7f0e",
    "ROBO DE VEHICULO": "#9467bd",
    "TACHA DE VEHICULO": "#2ca02c",
    "HOMICIDIO": "#000000",
}

# Si hay más puntos que este límite, se dibujan agrupados (clusters) para que el mapa no se ponga lento.
limite_puntos_individuales = 1500

# Campos que se piden a Solr para dibujar los puntos (fl = field list). Pedir solo lo necesario
# hace la respuesta mucho más liviana que pedir los 39 campos de cada documento.
campos_para_mapa = "latitud,longitud,delito,fecha,canton"


def crear_mapa(centro=None, zoom=8):
    if centro is None:
        centro = centro_costa_rica
    return folium.Map(location=centro, zoom_start=zoom, tiles="OpenStreetMap")


def agregar_herramienta_dibujo(mapa):
    """
    Agrega la barra de dibujo. Solo se habilitan polígonos y rectángulos: el polígono se dibuja
    haciendo clic en cada vértice y se cierra haciendo clic en el primero.
    """
    Draw(
        export=False,
        draw_options={
            "polygon": {"allowIntersection": False, "showArea": True},
            "rectangle": True,
            "polyline": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": False},
    ).add_to(mapa)


def agregar_puntos(mapa, documentos):
    """
    Dibuja los documentos devueltos por Solr como puntos.
    - Pocos puntos: un círculo por delito, con su color y un texto al pasar el mouse.
    - Muchos puntos: FastMarkerCluster los agrupa por cercanía y muestra cuántos hay en cada grupo.
    """
    if len(documentos) <= limite_puntos_individuales:
        for documento in documentos:
            delito = documento.get("delito", "")
            texto = delito + " | " + documento.get("canton", "") + " | " + documento.get("fecha", "")[:10]
            folium.CircleMarker(
                location=[documento["latitud"], documento["longitud"]],
                radius=4,
                color=colores_delito.get(delito, "#555555"),
                fill=True,
                fill_opacity=0.8,
                weight=1,
                tooltip=texto,
            ).add_to(mapa)
    else:
        coordenadas = []
        for documento in documentos:
            coordenadas.append([documento["latitud"], documento["longitud"]])
        FastMarkerCluster(coordenadas).add_to(mapa)


def agregar_leyenda_colores(columna_streamlit):
    """Muestra la leyenda de colores de los delitos debajo del mapa."""
    partes = []
    for delito in colores_delito:
        partes.append(
            "<span style='color:" + colores_delito[delito] + "; font-size:18px'>&#9679;</span> " + delito
        )
    columna_streamlit.markdown(" &nbsp; ".join(partes), unsafe_allow_html=True)


def obtener_poligono_dibujado(estado_mapa):
    """
    Busca el último polígono que el usuario dibujó en el mapa.
    streamlit-folium devuelve las figuras en formato GeoJSON, donde un polígono es una lista de
    anillos y cada anillo es una lista de puntos [longitud, latitud]. Se usa el anillo exterior.
    Devuelve la lista de vértices o None si no hay ningún polígono.
    """
    if estado_mapa is None:
        return None
    dibujos = estado_mapa.get("all_drawings")
    if dibujos is None or len(dibujos) == 0:
        return None

    ultimo = dibujos[len(dibujos) - 1]
    geometria = ultimo.get("geometry", {})
    if geometria.get("type") != "Polygon":
        return None
    return geometria["coordinates"][0]


def poligono_a_wkt(vertices):
    """
    Convierte los vértices al formato WKT (Well-Known Text), que es el que Solr usa para las
    consultas espaciales: POLYGON((lon1 lat1, lon2 lat2, ..., lon1 lat1)).
    - El orden de cada punto es LONGITUD y luego LATITUD (al revés de como se guarda "lat,lon").
    - El primer y el último vértice deben ser el mismo, para que el polígono quede cerrado.
    """
    puntos = []
    for vertice in vertices:
        puntos.append(str(round(vertice[0], 6)) + " " + str(round(vertice[1], 6)))

    if puntos[0] != puntos[len(puntos) - 1]:
        puntos.append(puntos[0])

    return "POLYGON((" + ", ".join(puntos) + "))"


def dibujar_poligono(mapa, vertices):
    """Dibuja el polígono en el mapa de resultados (Folium usa el orden latitud, longitud)."""
    puntos = []
    for vertice in vertices:
        puntos.append([vertice[1], vertice[0]])
    folium.Polygon(locations=puntos, color="#333333", weight=2, fill=False).add_to(mapa)
