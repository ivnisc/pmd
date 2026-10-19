"""Mapas con SQLAlchemy, GeoJSON y Matplotlib, siguiendo el Lab 05."""

import argparse
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(BASE / "data" / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import BoundaryNorm, PowerNorm, Normalize
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MplPath
import pandas as pd

from conexion import consulta


def dibujar(geometria, ax, **estilo):
    # los anillos interiores conservan los agujeros de los polígonos
    poligonos = (geometria["coordinates"] if geometria["type"] == "MultiPolygon"
                 else [geometria["coordinates"]])
    for poligono in poligonos:
        vertices, codigos = [], []
        for numero, anillo in enumerate(poligono):
            area = sum(a[0] * b[1] - b[0] * a[1]
                       for a, b in zip(anillo, anillo[1:]))
            if (area > 0) != (numero == 0):
                anillo = list(reversed(anillo))
            vertices.extend(anillo)
            codigos.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(anillo) - 2)
                           + [MplPath.CLOSEPOLY])
        ax.add_patch(PathPatch(MplPath(vertices, codigos), **estilo))


def geometrias():
    return consulta("""
        SELECT i,j,ST_AsGeoJSON(geom,9)::json AS geometria,
               ST_AsGeoJSON(ST_Transform(geom,4326),9)::json AS geojson
        FROM mv_grilla ORDER BY i,j
    """)


def comunas_recortadas():
    return consulta("""
        WITH caja AS (SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom FROM mv_grilla),
        recortes AS (
            SELECT c.comuna,ST_Intersection(c.geom,b.geom) AS geom
            FROM comunas_estudio c CROSS JOIN caja b
        )
        SELECT comuna,ST_AsGeoJSON(geom,9)::json AS geometria,
               ST_AsGeoJSON(ST_Transform(geom,4326),9)::json AS geojson,
               ST_Area(geom)/1e6 AS area_km2,
               ST_X(ST_PointOnSurface(geom)) AS x,
               ST_Y(ST_PointOnSurface(geom)) AS y
        FROM recortes ORDER BY comuna
    """)


def mapa_q6():
    datos = pd.read_csv(BASE / "q6_grilla.csv").merge(
        geometrias(), on=["i", "j"], validate="one_to_one")
    comunas = comunas_recortadas()
    top = datos.loc[datos.top10].sort_values("orden")
    assert len(datos) == 636 and len(top) == 10 and datos.edificios.sum() == 118888
    fc = {"type": "FeatureCollection", "features": []}
    for fila in datos.to_dict("records"):
        g = fila.pop("geojson")
        fila.pop("geometria")
        fc["features"].append({"type": "Feature", "geometry": g, "properties": fila})
    (BASE / "q6_grilla.geojson").write_text(json.dumps(
        fc, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")

    fig, ejes = plt.subplots(1, 2, figsize=(6.6, 4.5))
    fig.subplots_adjust(left=0.015, right=0.985, bottom=0.25, top=0.83, wspace=0.05)
    bordes = consulta("""
        SELECT ST_XMin(ST_Extent(geom)) AS xmin,ST_XMax(ST_Extent(geom)) AS xmax,
               ST_YMin(ST_Extent(geom)) AS ymin,ST_YMax(ST_Extent(geom)) AS ymax FROM mv_grilla
    """).iloc[0]
    for numero, (ax, variable, titulo, cmap, norma) in enumerate(zip(
        ejes, ["edificios", "rutas"], ["Edificios OSM", "Rutas GTFS distintas"],
        [plt.get_cmap("YlGnBu"), plt.get_cmap("YlGnBu")],
        [PowerNorm(0.5, vmin=0, vmax=2600), Normalize(vmin=0, vmax=80)]
    )):
        for fila in datos.itertuples():
            dibujar(fila.geometria, ax, facecolor=cmap(norma(getattr(fila, variable))),
                    edgecolor="#dddddd", linewidth=0.12, zorder=1)
        for fila in comunas.itertuples():
            dibujar(fila.geometria, ax, facecolor="none", edgecolor="#777777",
                    linewidth=0.35, zorder=2)
            if numero == 1 and fila.area_km2 >= 12:
                ax.text(fila.x, fila.y, fila.comuna.replace(" ", "\n"), ha="center", va="center",
                        fontsize=5.7, color="#333333", zorder=3, linespacing=0.95,
                        path_effects=[pe.withStroke(linewidth=1.7, foreground="white")])
        for fila in top.itertuples():
            dibujar(fila.geometria, ax, facecolor="none", edgecolor="#d10069", linewidth=1.1, zorder=4)
            if numero == 0:
                # la consulta entrega un punto garantizado dentro de la celda
                punto = consulta("SELECT ST_X(ST_PointOnSurface(geom)) AS x,"
                                 " ST_Y(ST_PointOnSurface(geom)) AS y FROM mv_grilla WHERE i=:i AND j=:j",
                                 i=fila.i, j=fila.j).iloc[0]
                ax.text(punto.x, punto.y, str(fila.orden), ha="center", va="center", fontsize=6,
                        fontweight="bold", color="#a50053", zorder=5,
                        path_effects=[pe.withStroke(linewidth=1.6, foreground="white")])
        ax.set(xlim=(bordes.xmin - 180, bordes.xmax + 180),
               ylim=(bordes.ymin - 180, bordes.ymax + 180), aspect="equal")
        ax.set_axis_off()
        ax.set_title(titulo, fontsize=9, pad=7)
        x, y = bordes.xmin + 700, bordes.ymin + 650
        ax.plot([x, x + 5000], [y, y], color="white", lw=3.5, zorder=6)
        ax.plot([x, x + 5000], [y, y], color="#222222", lw=1.3, zorder=7)
        ax.text(x + 2500, y + 250, "5 km", ha="center", fontsize=6.5, zorder=7,
                path_effects=[pe.withStroke(linewidth=1.8, foreground="white")])
        barra_ax = fig.add_axes([0.075 + numero * 0.5, 0.19, 0.35, 0.022])
        ticks = [0, 100, 500, 1000, 2500] if numero == 0 else [0, 20, 40, 60, 80]
        barra = fig.colorbar(plt.cm.ScalarMappable(norm=norma, cmap=cmap), cax=barra_ax,
                            orientation="horizontal", ticks=ticks)
        barra.ax.tick_params(labelsize=6.5, length=2)
        barra.set_label("Edificios (escala de raíz cuadrada)" if numero == 0 else "Rutas (escala lineal)",
                        fontsize=7, labelpad=3)
    fig.suptitle("Construcciones y trazados de transporte público", fontsize=10, y=0.975)
    fig.text(0.5, 0.92, "Grilla hexagonal de lado 500 m · Top 10: edificios ↓; rutas ↑ como desempate",
             fontsize=7.5, ha="center")
    fig.legend(handles=[Patch(facecolor="none", edgecolor="#d10069", linewidth=1.2,
                              label="Diez celdas seleccionadas; numeración según el orden de Q6")],
               loc="lower center", bbox_to_anchor=(0.5, 0.065), frameon=False, fontsize=7)
    fig.text(0.5, 0.018,
             "Fuentes: OSM 12-10-2026 · GTFS V168.20261003 (descarga 13-10-2026) · DPA 2023\n"
             "EPSG:5361. Celdas recortadas al borde; conteos sin ponderación por área ni población.",
             ha="center", fontsize=6.5, color="#444444", linespacing=1.4)
    guardar(fig, 6)
    print("Q6: mapa_q6.pdf y q6_grilla.geojson; 636 celdas y top 10.")


def guardar(fig, pregunta):
    fig.savefig(BASE / f"mapa_q{pregunta}.pdf", metadata={"Title": f"Mapa de Q{pregunta}"})
    vista = BASE / "data" / "interim" / "mapas"
    vista.mkdir(parents=True, exist_ok=True)
    fig.savefig(vista / f"mapa_q{pregunta}.png", dpi=220)
    plt.close(fig)


def mapa_q7():
    sectores = pd.read_csv(BASE / "q7_sectores.csv")
    sectores = sectores.loc[sectores.franja.eq("madrugada")].copy()
    sectores = sectores.merge(geometrias(), on=["i", "j"], validate="many_to_one")
    comunas = comunas_recortadas()
    assert len(sectores) == 1048 and not sectores.duplicated(["noche", "i", "j"]).any()
    assert sectores.horas_con_oferta.between(0, 6).all()

    elementos = []
    for fila in sectores.to_dict("records"):
        g = fila.pop("geojson")
        fila.pop("geometria")
        propiedades = {k: (None if pd.isna(v) else v) for k, v in fila.items()}
        elementos.append({"type": "Feature", "geometry": g,
                          "properties": {"capa": "sector", **propiedades}})
    for fila in comunas.to_dict("records"):
        elementos.append({"type": "Feature", "geometry": fila["geojson"],
                          "properties": {"capa": "comuna", "comuna": fila["comuna"]}})
    coleccion = {"type": "FeatureCollection", "features": elementos}
    (BASE / "q7_sectores.geojson").write_text(
        json.dumps(coleccion, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
                         "pdf.fonttype": 42, "hatch.linewidth": 0.35})
    fig, ejes = plt.subplots(1, 2, figsize=(6.6, 5.0))
    fig.subplots_adjust(left=0.015, right=0.985, bottom=0.29, top=0.83, wspace=0.035)
    cmap = plt.get_cmap("cividis_r", 7)
    norma = BoundaryNorm([x - 0.5 for x in range(8)], cmap.N)
    limites = consulta("""
        SELECT ST_XMin(ST_Extent(geom)) AS xmin,ST_XMax(ST_Extent(geom)) AS xmax,
               ST_YMin(ST_Extent(geom)) AS ymin,ST_YMax(ST_Extent(geom)) AS ymax
        FROM mv_grilla
    """).iloc[0]
    titulos = [("2026-10-16", "Sábado 17 de octubre", 46),
               ("2026-10-17", "Domingo 18 de octubre", 52)]
    for ax, (noche, titulo, esperados) in zip(ejes, titulos):
        for fila in comunas.itertuples():
            dibujar(fila.geometria, ax, facecolor="#fafafa", edgecolor="none", zorder=0)
        datos = sectores.loc[sectores.noche.eq(noche)]
        sin_paradas = datos.paradas_bus_en_celda.eq(0)
        parciales = (~sin_paradas & datos.horas_con_oferta.lt(6)).sum()
        assert len(datos) == 524 and sin_paradas.sum() == 33 and parciales == esperados
        for fila in datos.itertuples():
            if fila.paradas_bus_en_celda == 0:
                estilo = {"facecolor": "#dedede", "edgecolor": "#858585", "hatch": "////"}
            else:
                estilo = {"facecolor": cmap(norma(fila.horas_con_oferta)),
                          "edgecolor": "#ffffff"}
            dibujar(fila.geometria, ax, linewidth=0.12, zorder=1, **estilo)
        for fila in comunas.itertuples():
            dibujar(fila.geometria, ax, facecolor="none", edgecolor="#555555",
                    linewidth=0.38, zorder=2)
            if fila.area_km2 >= 12:
                nombre = fila.comuna.replace(" ", "\n")
                ax.text(fila.x, fila.y, nombre, ha="center", va="center", fontsize=6,
                        color="#222222", linespacing=0.95, zorder=3,
                        path_effects=[pe.withStroke(linewidth=1.7, foreground="white")])
        ax.set(xlim=(limites.xmin - 180, limites.xmax + 180),
               ylim=(limites.ymin - 180, limites.ymax + 180), aspect="equal")
        ax.set_axis_off()
        ax.set_title(f"{titulo}\n{parciales} celdas con alguna hora sin oferta", fontsize=8.2, pad=7)
        x, y = limites.xmin + 700, limites.ymin + 650
        ax.plot([x, x + 5000], [y, y], color="white", lw=3.5, zorder=4)
        ax.plot([x, x + 5000], [y, y], color="#222222", lw=1.3, zorder=5)
        for dx in [0, 5000]:
            ax.plot([x + dx, x + dx], [y - 130, y + 130], color="#222222", lw=0.8, zorder=5)
        ax.text(x + 2500, y + 230, "5 km", ha="center", fontsize=6.5,
                path_effects=[pe.withStroke(linewidth=2, foreground="white")], zorder=5)

    fig.suptitle("Oferta de buses de madrugada en sectores residenciales", fontsize=10, y=0.975)
    fig.text(0.5, 0.918, "00:00–06:00 · Celdas hexagonales de lado 500 m · Octubre de 2026",
             ha="center", fontsize=8)
    barra_ax = fig.add_axes([0.25, 0.205, 0.5, 0.022])
    barra = fig.colorbar(plt.cm.ScalarMappable(norm=norma, cmap=cmap), cax=barra_ax,
                        orientation="horizontal", ticks=range(7))
    barra.set_label("Horas con alguna oferta en paraderos interiores (de 6)", fontsize=7.5, labelpad=4)
    barra.ax.tick_params(labelsize=7, length=2)
    fig.legend(handles=[Patch(facecolor="#dedede", edgecolor="#858585", hatch="////",
                              label="Celda residencial sin paraderos interiores (33)"),
                        Patch(facecolor="#fafafa", edgecolor="#777777",
                              label="Sin objetos OSM de los tipos residenciales seleccionados")],
               loc="lower center", bbox_to_anchor=(0.5, 0.065), frameon=False,
               fontsize=7, handlelength=1.8, labelspacing=0.5)
    fig.text(0.5, 0.025,
             "Fuentes: OSM 12-10-2026 · GTFS V168.20261003 (descarga 13-10-2026) · DPA 2023\n"
             "EPSG:5361. Oferta programada; no mide cumplimiento, espera ni acceso peatonal.",
             ha="center", fontsize=6.5, color="#444444", linespacing=1.4)
    guardar(fig, 7)
    print("Q7: mapa_q7.pdf y q7_sectores.geojson; 524 celdas por madrugada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preguntas", type=int, choices=[6, 7], nargs="*", default=[6, 7])
    args = parser.parse_args()
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "pdf.fonttype": 42})
    for pregunta in args.preguntas:
        {6: mapa_q6, 7: mapa_q7}[pregunta]()
