"""
ETL — Integrante 2 — SICOP (inversión municipal ambiental)

Aporta el Factor de Inversión Municipal (25%) del Índice de Viabilidad, a
partir de los contratos públicos que el Módulo de Descarga de Datos (Datos
Abiertos) de SICOP publica sin token.

Este archivo es solo la puerta de entrada: interpreta los argumentos y
coordina los demás módulos de la carpeta.

    reportes.py         qué reportes existen, sus códigos y sus filtros
    descarga_sicop.py   hablar con la API de SICOP (solicitar/esperar/bajar)
    confirmacion.py     el código por correo que SICOP exige antes de construir
    clasificacion.py    el criterio de "contrato ambiental", por palabras clave
    normalizacion.py    unir las cuatro tablas y armar las filas finales
    carga_postgres.py   escribir en `contratos_ambientales`
    factor_inversion.py calcular el puntaje por cantón

Uso:
    python sync_sicop.py --listar-reportes
    python sync_sicop.py --criterio
    python sync_sicop.py --solicitar --todos --desde 2026-06-01 --hasta 2026-09-01 \
                         --correo yo@ejemplo.com
    python sync_sicop.py --confirmar --codigo Lw45ef      # ubica solo el reporte
    python sync_sicop.py --pendientes
    python sync_sicop.py --descargar --report-id 36713 --reporte contratos
    python sync_sicop.py --cargar --dry-run
    python sync_sicop.py --cargar --calcular-factor
"""
import argparse
import glob
import os
import sys
from datetime import date, timedelta

# La consola de Windows usa cp1252 y rompe los nombres con tilde.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# etl/common/db.py es compartido por las cuatro fuentes del proyecto y no es un
# paquete instalable, así que se agrega su carpeta al path.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "common"))

from carga_postgres import cargar_contratos  # noqa: E402
from clasificacion import resumen_criterio  # noqa: E402
from confirmacion import (  # noqa: E402
    adivinar_reporte,
    confirmar_codigo,
    leer_solicitud,
    listar_pendientes,
    solicitar_codigo,
)
from db import get_connection, registrar_sincronizacion  # noqa: E402
from descarga_sicop import DIR_DATOS, descargar, esperar, solicitar  # noqa: E402
from factor_inversion import calcular_factor_inversion  # noqa: E402
from normalizacion import cargar_tablas, construir_dataset  # noqa: E402
from reportes import FORMATOS, REPORTES, REPORTES_DEL_PROYECTO, URL_MODULO  # noqa: E402


def listar_reportes():
    print("\nReportes del Módulo de Descarga de Datos de SICOP")
    print("  {}".format(URL_MODULO))
    print(
        "\n{:<16} {:<14} {:<32} {:<7} {}".format(
            "nombre", "código", "sección", "fechas", "usa"
        )
    )
    for nombre, cfg in REPORTES.items():
        print(
            "{:<16} {:<14} {:<32} {:<7} {}".format(
                nombre,
                cfg["codigo"],
                cfg["seccion"][:32],
                "sí" if cfg["usa_fechas"] else "no",
                "SÍ" if cfg["usa"] else "-",
            )
        )
    print("\nDetalle de cada uno:")
    for nombre, cfg in REPORTES.items():
        print("\n  {} ({})".format(nombre, cfg["codigo"]))
        print("    {}".format(cfg["descripcion"]))


def solicitar_reportes(nombres, formato, desde, hasta, correo=None):
    """
    Encola cada reporte y, si se pasó --correo, pide de una vez el código de
    confirmación que SICOP necesita para empezar a construirlo.

    Sin confirmar, un reporte se queda en 'msg_not_builded_report' de forma
    indefinida: se comprobó dejando uno encolado 45 minutos. Por eso, sin
    --correo, este comando solo encola y avisa qué falta.
    """
    rutas = []
    pendientes = []
    for nombre in nombres:
        cfg = REPORTES[nombre]
        print("\n>>> {} — {} ({})".format(nombre, cfg["seccion"], cfg["codigo"]))

        if correo is None:
            datos = solicitar(
                nombre,
                formato=formato,
                desde=desde if cfg["usa_fechas"] else None,
                hasta=hasta if cfg["usa_fechas"] else None,
            )
            report_id = datos["reportId"]
            print(
                "  encolado -> reportId={} status={}".format(
                    report_id, datos.get("status")
                )
            )
            pendientes.append((nombre, report_id, None))
            continue

        # Con correo: encolar, pedir el código y esperar a que llegue.
        datos = solicitar(
            nombre,
            formato=formato,
            desde=desde if cfg["usa_fechas"] else None,
            hasta=hasta if cfg["usa_fechas"] else None,
        )
        report_id = datos["reportId"]
        confirm_id = solicitar_codigo(
            report_id, cfg["codigo"], correo, solicitud=datos.get("_solicitud")
        )
        print(
            "  encolado -> reportId={}; código enviado a {} "
            "(confirmId {})".format(report_id, correo, confirm_id)
        )
        pendientes.append((nombre, report_id, confirm_id))

    print(
        "\nEncolados: {}".format(
            ", ".join("{} ({})".format(n, r) for n, r, _ in pendientes)
        )
    )
    print(
        "\nFalta confirmar el código que SICOP envió por correo. Llega uno por\n"
        "reporte y NO dice a cuál pertenece, así que conviene no pasar\n"
        "--report-id y dejar que el script lo ubique — una vez por cada código:"
    )
    for _ in pendientes:
        print("  python sync_sicop.py --confirmar --codigo <código del correo>")
    if correo is None:
        print(
            "\n(o vuelva a correr con --correo <su correo> para que el script "
            "pida el código solo)"
        )
    return rutas


def _nombre_por_codigo(code_report):
    """SV_CONT_0014 -> 'contratos'."""
    for nombre, cfg in REPORTES.items():
        if cfg["codigo"] == code_report:
            return nombre
    return code_report


def mostrar_pendientes():
    """
    Muestra qué reportId corresponde a qué reporte, para no tener que adivinar
    cuál de los correos de SICOP va con cuál.
    """
    solicitudes = listar_pendientes()
    if not solicitudes:
        print(
            "\nNo hay solicitudes registradas. Pida una con:\n"
            "  python sync_sicop.py --solicitar --todos --correo <su correo>"
        )
        return

    print("\nSolicitudes de descarga registradas")
    print("{:<10} {:<16} {:<14} {:<22} {}".format(
        "reportId", "reporte", "código", "solicitado (UTC)", "estado"))
    for s in solicitudes:
        print("{:<10} {:<16} {:<14} {:<22} {}".format(
            s.get("reportId", "?"),
            _nombre_por_codigo(s.get("codeReport", "")),
            s.get("codeReport", ""),
            (s.get("fecha") or "")[:19],
            "descargado" if s.get("descargado") else "falta confirmar",
        ))
    print(
        "\nEl correo de SICOP NO dice a qué reporte pertenece cada código: "
        "llega con el asunto\n'Código verificación para reporte', sin enlace y "
        "sin el número de reporte. Si se\npiden los tres reportes seguidos, "
        "además los tres correos llegan con segundos\nde diferencia, así que "
        "la hora tampoco desempata."
    )
    if any(not s.get("descargado") for s in solicitudes):
        print(
            "\nPor eso conviene confirmar sin --report-id y dejar que el "
            "script ubique el reporte:\n"
            "  python sync_sicop.py --confirmar --codigo <código del correo>"
        )


def confirmar_y_bajar(nombre, report_id, codigo, formato, espera_max):
    """
    Confirma el código recibido por correo y, ya con el reporte
    construyéndose, espera y lo baja. Es el paso que cierra el ciclo.

    No hace falta pasar --reporte: al pedir el código se guardó en
    `data/<reportId>.confirm.json` a qué reporte corresponde ese número, así
    que basta el reportId que viene en el enlace del correo (`?processId=`).
    """
    solicitud = leer_solicitud(report_id)

    if nombre:
        code_report = REPORTES[nombre]["codigo"]
        # Si el guardado dice otra cosa, gana el guardado: significa que se
        # confundió el reportId de un reporte con el nombre de otro, y mandar
        # el processType equivocado hace que SICOP rechace el código con un
        # error que no explica nada.
        if solicitud and solicitud.get("codeReport") != code_report:
            print(
                "  aviso: el reportId {} se pidió para '{}' ({}), no para "
                "'{}'. Se usa el guardado.".format(
                    report_id,
                    _nombre_por_codigo(solicitud["codeReport"]),
                    solicitud["codeReport"],
                    nombre,
                )
            )
            code_report = solicitud["codeReport"]
            nombre = _nombre_por_codigo(code_report)
    elif solicitud:
        code_report = solicitud["codeReport"]
        nombre = _nombre_por_codigo(code_report)
        print("  reportId {} corresponde a '{}' ({})".format(report_id, nombre, code_report))
    else:
        raise ValueError(
            "No hay una solicitud guardada para el reportId {}. Pase --reporte "
            "para indicar de cuál es, o vuelva a pedir el código con "
            "--solicitar.".format(report_id)
        )

    confirmar_codigo(report_id, code_report, codigo)
    print("  código aceptado; SICOP empezó a construir el reporte {}".format(report_id))

    if not esperar(report_id, espera_max=espera_max):
        print(
            "  todavía no está listo. Retome con: python sync_sicop.py "
            "--descargar --report-id {} --reporte {}".format(report_id, nombre)
        )
        return None
    ruta = descargar(report_id, nombre, formato)
    print("  guardado: {}".format(ruta))
    return ruta


def archivos_locales(rutas_o_patrones):
    """Expande rutas y comodines; si no se pasó nada, usa todo `data/`."""
    if not rutas_o_patrones:
        patrones = [os.path.join(DIR_DATOS, "*")]
    else:
        patrones = rutas_o_patrones

    rutas = []
    for patron in patrones:
        encontrados = sorted(glob.glob(patron))
        if not encontrados and os.path.exists(patron):
            encontrados = [patron]
        for ruta in encontrados:
            if os.path.isfile(ruta) and not ruta.endswith(
                (".meta.json", ".confirm.json", ".gitkeep")
            ):
                rutas.append(ruta)
    return rutas


def cargar(rutas, solo_municipalidades, dry_run, desde, hasta):
    print("\nLeyendo reportes descargados:")
    tablas = cargar_tablas(rutas)
    if not tablas:
        raise ValueError(
            "No se pudo leer ningún reporte. Baje los reportes primero con "
            "'python sync_sicop.py --solicitar --todos'."
        )

    df, stats = construir_dataset(tablas, solo_municipalidades=solo_municipalidades)

    print("\nResultado de la clasificación:")
    for clave in (
        "contratos",
        "carteles",
        "instituciones",
        "contratos_sin_lineas",
        "contratos_sin_cartel",
        "contratos_sin_institucion",
        "descartados_no_municipales",
        "evaluados",
        "ambientales",
        "no_ambientales",
    ):
        if clave in stats:
            print("  {:<28} {}".format(clave, stats[clave]))

    if len(df):
        print("\nContratos ambientales por categoría detectada:")
        for categoria, cantidad in df["categoria_detectada"].value_counts().items():
            monto = df.loc[df["categoria_detectada"] == categoria, "monto"].sum()
            print("  {:<22} {:>5} contratos  {:>18,.2f}".format(
                categoria, cantidad, monto))

    if dry_run:
        print(
            "\ndry-run: {} contratos ambientales detectados, sin tocar la "
            "base".format(len(df))
        )
        if len(df):
            print("\nMuestra (primeras 5 filas):")
            for _, fila in df.head(5).iterrows():
                print(
                    "  [{}] {} | {} | {:,.2f} {} | {}".format(
                        fila["categoria_detectada"],
                        str(fila["institucion"])[:34],
                        str(fila["canton"])[:16],
                        float(fila["monto"]),
                        fila["moneda"],
                        str(fila["descripcion_objeto"])[:60],
                    )
                )
        return len(df)

    with get_connection() as conn:
        insertados, sin_canton, borrados = cargar_contratos(
            conn, df, desde=desde, hasta=hasta
        )
        registrar_sincronizacion(
            conn,
            fuente_codigo="SICOP",
            estado="exito" if insertados else "parcial",
            registros_procesados=insertados,
            mensaje=(
                "periodo {} a {}; evaluados {}, ambientales {}, "
                "sin cantón {}, reemplazados {}; archivos: {}".format(
                    desde,
                    hasta,
                    stats.get("evaluados", 0),
                    stats.get("ambientales", 0),
                    sin_canton,
                    borrados,
                    ", ".join(os.path.basename(r) for r in rutas),
                )
            ),
        )

    print(
        "\nOK: {} contratos ambientales cargados ({} sin cantón resuelto, "
        "{} filas del periodo reemplazadas)".format(insertados, sin_canton, borrados)
    )
    return insertados


def main():
    hoy = date.today()
    parser = argparse.ArgumentParser(
        description="ETL SICOP (datos abiertos -> clasificación -> PostgreSQL)"
    )
    parser.add_argument(
        "--listar-reportes",
        action="store_true",
        help="Muestra el catálogo de reportes de SICOP y sus códigos",
    )
    parser.add_argument(
        "--criterio",
        action="store_true",
        help="Imprime el criterio de clasificación ambiental usado",
    )
    parser.add_argument(
        "--solicitar",
        action="store_true",
        help="Encola en SICOP los reportes (con --correo pide el código)",
    )
    parser.add_argument(
        "--todos",
        action="store_true",
        help="Con --solicitar: pide los tres reportes que usa el proyecto",
    )
    parser.add_argument(
        "--reporte",
        action="append",
        choices=sorted(REPORTES),
        help="Reporte a solicitar o a descargar (repetible)",
    )
    parser.add_argument(
        "--correo",
        help=(
            "Correo al que SICOP manda el código de confirmación. Es el único "
            "dato personal del ETL y solo se usa en esta llamada: no se guarda "
            "ni se versiona"
        ),
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help=(
            "Confirma el código recibido por correo y baja el reporte. "
            "Sin --report-id, prueba el código contra las solicitudes "
            "pendientes"
        ),
    )
    parser.add_argument(
        "--codigo",
        help=(
            "Código que llegó al correo. 6-7 caracteres alfanuméricos y "
            "distingue mayúsculas (p. ej. 'Lw45ef'), no son dígitos"
        ),
    )
    parser.add_argument(
        "--pendientes",
        action="store_true",
        help="Muestra qué reportId corresponde a qué reporte y cuáles faltan confirmar",
    )
    parser.add_argument(
        "--descargar",
        action="store_true",
        help="Baja un reporte ya construido, por --report-id",
    )
    parser.add_argument("--report-id", type=int, help="reportId devuelto por SICOP")
    parser.add_argument(
        "--formato", default="csv", choices=list(FORMATOS), help="Formato del archivo"
    )
    parser.add_argument(
        "--desde",
        default=str(hoy - timedelta(days=90)),
        help="Inicio del rango (YYYY-MM-DD). Por defecto, 90 días atrás",
    )
    parser.add_argument(
        "--hasta", default=str(hoy), help="Fin del rango (YYYY-MM-DD). Por defecto, hoy"
    )
    parser.add_argument(
        "--espera",
        type=int,
        default=None,
        help="Segundos máximos de espera por reporte (default: SICOP_ESPERA_MAX)",
    )
    parser.add_argument(
        "--cargar",
        action="store_true",
        help="Procesa los reportes de data/ y carga en PostgreSQL",
    )
    parser.add_argument(
        "--archivo",
        action="append",
        help="Archivo o comodín a procesar (repetible). Default: data/*",
    )
    parser.add_argument(
        "--todas-instituciones",
        action="store_true",
        help=(
            "No filtrar a gobiernos locales. Cambia el significado del factor: "
            "ver la nota de alcance en docs/sicop.md"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Clasifica y reporta, sin escribir en la base de datos",
    )
    parser.add_argument(
        "--calcular-factor",
        action="store_true",
        help="Crea/recrea la vista v_factor_inversion y muestra el ranking",
    )
    args = parser.parse_args()

    if not any(
        [
            args.listar_reportes,
            args.criterio,
            args.solicitar,
            args.pendientes,
            args.confirmar,
            args.descargar,
            args.cargar,
            args.calcular_factor,
        ]
    ):
        parser.print_help()
        return

    if args.listar_reportes:
        listar_reportes()
    if args.criterio:
        print()
        print(resumen_criterio())
    if args.pendientes:
        mostrar_pendientes()

    desde = date.fromisoformat(args.desde)
    hasta = date.fromisoformat(args.hasta)

    try:
        if args.solicitar:
            nombres = REPORTES_DEL_PROYECTO if args.todos else (args.reporte or [])
            if not nombres:
                parser.error("--solicitar requiere --todos o al menos un --reporte")
            solicitar_reportes(
                nombres, args.formato, desde, hasta, correo=args.correo
            )

        if args.confirmar:
            if not args.codigo:
                parser.error("--confirmar requiere --codigo")

            if args.report_id:
                # --reporte es opcional: el reporte se deduce de
                # data/<reportId>.confirm.json, escrito al pedir el código.
                confirmar_y_bajar(
                    (args.reporte or [None])[0],
                    args.report_id,
                    args.codigo,
                    args.formato,
                    args.espera,
                )
            else:
                # Sin --report-id: el correo de SICOP no dice a qué reporte
                # pertenece el código, así que se prueba contra los pendientes.
                print(
                    "\nEl correo de SICOP no identifica el reporte. Probando "
                    "el código contra las solicitudes pendientes..."
                )
                solicitud = adivinar_reporte(args.codigo)
                if solicitud is None:
                    parser.error(
                        "Ninguna solicitud pendiente aceptó ese código. "
                        "Verifique que esté completo y respetando mayúsculas "
                        "(son 6-7 caracteres alfanuméricos, p. ej. 'Lw45ef'), "
                        "o revise 'python sync_sicop.py --pendientes'."
                    )
                report_id = solicitud["reportId"]
                nombre = _nombre_por_codigo(solicitud["codeReport"])
                print("  código aceptado para '{}' (reportId {})".format(
                    nombre, report_id))
                if not esperar(report_id, espera_max=args.espera):
                    print(
                        "  todavía no está listo. Retome con: python "
                        "sync_sicop.py --descargar --report-id {} --reporte "
                        "{}".format(report_id, nombre)
                    )
                else:
                    ruta = descargar(
                        report_id,
                        nombre,
                        args.formato,
                        metadatos=solicitud.get("solicitud"),
                    )
                    print("  guardado: {}".format(ruta))

        if args.descargar:
            if not args.report_id:
                parser.error("--descargar requiere --report-id")

            solicitud = leer_solicitud(args.report_id) or {}
            nombre = (args.reporte or [None])[0] or (
                _nombre_por_codigo(solicitud["codeReport"])
                if solicitud.get("codeReport")
                else None
            )

            # Esperar antes de bajar. Un reporte confirmado pero todavía en
            # construcción responde al endpoint de descarga con HTTP 500, un
            # error genérico que no dice que falte esperar. Se pregunta primero
            # con checkDownload, que sí lo distingue.
            if not esperar(args.report_id, espera_max=args.espera):
                print(
                    "  sigue construyéndose. Vuelva a correr el mismo comando "
                    "más tarde; el reporte no se pierde."
                )
            else:
                ruta = descargar(
                    args.report_id,
                    nombre,
                    args.formato,
                    metadatos=solicitud.get("solicitud"),
                )
                print("guardado: {}".format(ruta))

        if args.cargar:
            rutas = archivos_locales(args.archivo)
            if not rutas:
                parser.error(
                    "No hay archivos que procesar en {}. Corra --solicitar "
                    "primero.".format(DIR_DATOS)
                )
            cargar(
                rutas,
                solo_municipalidades=not args.todas_instituciones,
                dry_run=args.dry_run,
                desde=desde,
                hasta=hasta,
            )

        if args.calcular_factor:
            calcular_factor_inversion()

    except Exception as exc:
        # El log de `sincronizaciones` es el mecanismo de trazabilidad del
        # proyecto: un fallo del ETL también tiene que quedar registrado.
        if not args.dry_run:
            try:
                with get_connection() as conn:
                    registrar_sincronizacion(
                        conn, fuente_codigo="SICOP", estado="error", mensaje=str(exc)
                    )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
