import { useEffect, useMemo, useState } from "react";
import { obtenerFactorConectividad, type FactorConectividad, type InfraestructuraOsm } from "../../api";
import { CACHE_DIAS_DEFECTO, estiloCategoria, ORDEN_CATEGORIAS } from "../estilos";
import { useInfraestructuraOsm } from "../hooks/useInfraestructuraOsm";

interface PanelProps {
  cantonSeleccionado: number | null;
  onSeleccionarCanton: (cantonId: number | null) => void;
  /** Solo se muestra cuando el usuario está viendo OSM. */
  activo: boolean;
}

const GRIS = "var(--color-texto-suave)";

export default function PanelInfraestructuraCanton({
  cantonSeleccionado,
  onSeleccionarCanton,
  activo,
}: PanelProps) {
  const [todos, setTodos] = useState<FactorConectividad[]>([]);
  const [error, setError] = useState<string | null>(null);

  // El desglose de los 84 cantones se pide una sola vez: son 84 filas de
  // números, y así el panel responde al instante a cada clic — mismo
  // criterio que PanelBusquedaCanton (SNIT) y PanelInversionCanton (SICOP).
  useEffect(() => {
    obtenerFactorConectividad()
      .then(setTodos)
      .catch((e) => setError(e instanceof Error ? e.message : "Error desconocido"));
  }, []);

  const detalle = useMemo(
    () => todos.find((c) => c.canton_id === cantonSeleccionado) ?? null,
    [todos, cantonSeleccionado],
  );

  // Los POIs sí se piden por cantón: son varios cientos en todo el país y
  // solo se necesitan los del que está abierto.
  const { pois, cargando: cargandoPois } = useInfraestructuraOsm(
    activo ? cantonSeleccionado : null,
  );

  const porCategoria = useMemo(() => {
    const mapa = new Map<string, InfraestructuraOsm[]>();
    for (const poi of pois) {
      const lista = mapa.get(poi.categoria) ?? [];
      lista.push(poi);
      mapa.set(poi.categoria, lista);
    }
    return ORDEN_CATEGORIAS.map((categoria) => [categoria, mapa.get(categoria) ?? []] as const).filter(
      ([, filas]) => filas.length > 0,
    );
  }, [pois]);

  if (!activo) return null;

  // El error se muestra aunque no haya cantón seleccionado: si la vista
  // v_factor_conectividad todavía no existe, la API responde 503 con el
  // comando que falta correr, y esconderlo dejaría el panel mudo para
  // siempre — mismo criterio que PanelInversionCanton (SICOP).
  if (!detalle) {
    return error ? (
      <div className="panel-flotante">
        <h3 style={{ marginBottom: "0.4rem" }}>Factor de Conectividad (OSM)</h3>
        <p className="panel-error">{error}</p>
      </div>
    ) : null;
  }

  return (
    <div className="panel-flotante">
      <div className="panel-header">
        <h3>
          {detalle.nombre}
          <span className="panel-subt"> · {detalle.provincia}</span>
        </h3>
        <button className="panel-cerrar" onClick={() => onSeleccionarCanton(null)} title="Cerrar">
          ✕
        </button>
      </div>

      <p className="panel-resumen">
        Factor de Conectividad <strong>{Number(detalle.factor_conectividad).toFixed(1)}</strong>
        {" · "}
        {detalle.total_pois} {detalle.total_pois === 1 ? "punto de interés" : "puntos de interés"}
      </p>

      {detalle.total_pois === 0 ? (
        // Un cantón sin POIs no es necesariamente un dato faltante: puede ser
        // que de verdad no tenga nada mapeado en OSM, o que falte correr el
        // ETL (cargar_todos_los_cantones.py) para él.
        <p style={{ color: GRIS, margin: 0 }}>
          Sin infraestructura de OSM cargada para este cantón. El factor de conectividad queda
          en 0 mientras tanto — puede ser que el cantón no tenga nada mapeado en OSM, o que
          falte correr <code>etl/osm/cargar_todos_los_cantones.py</code> para él.
        </p>
      ) : (
        <>
          <SubConteo etiqueta="Centros de acopio" valor={detalle.pois_centro_acopio} />
          <SubConteo etiqueta="Escuelas" valor={detalle.pois_escuela} />
          <SubConteo etiqueta="Vías principales" valor={detalle.pois_via_principal} />

          {error && <p className="panel-error">{error}</p>}

          {cargandoPois ? (
            <p style={{ color: GRIS }}>Cargando puntos de interés…</p>
          ) : (
            porCategoria.map(([categoria, filas]) => {
              const { color, etiqueta } = estiloCategoria(categoria);
              return (
                <div key={categoria} style={{ marginTop: "0.6rem" }}>
                  <h4 className="panel-seccion-titulo" style={{ color, margin: "0 0 0.35rem" }}>
                    {etiqueta} ({filas.length})
                  </h4>
                  <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
                    {filas.map((poi) => (
                      <li key={poi.poi_id} className="panel-lista-item">
                        <span
                          aria-hidden
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: "50%",
                            background: color,
                            flexShrink: 0,
                          }}
                        />
                        {poi.nombre ?? "Sin nombre"}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })
          )}
        </>
      )}

      <p className="panel-nota">
        Fuente: OpenStreetMap / Overpass API — centros de acopio, escuelas y vías principales
        dentro del cantón, con caché de {CACHE_DIAS_DEFECTO} días (ver docs/osm.md). El factor
        de conectividad compara cuántos puntos tiene este cantón contra los otros 83, con y sin
        datos: 100 es el que más tiene, 0 el que menos (o ninguno) — no es un indicador oficial.
      </p>
    </div>
  );
}

function SubConteo({ etiqueta, valor }: { etiqueta: string; valor: number }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        fontSize: "0.78rem",
        color: GRIS,
        marginTop: "0.3rem",
      }}
    >
      <span>{etiqueta}</span>
      <span style={{ color: "var(--color-texto)", fontWeight: 600 }}>{valor}</span>
    </div>
  );
}
