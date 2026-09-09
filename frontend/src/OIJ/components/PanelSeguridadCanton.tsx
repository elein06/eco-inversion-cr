import { useEffect, useMemo, useState } from "react";
import {
  obtenerEstadisticasPorCanton,
  obtenerFactorSeguridad,
  type EstadisticaSeguridad,
  type FactorSeguridad,
} from "../../api";
import { COLOR_ACENTO, formatearTasa } from "../estilos";

interface PanelProps {
  cantonSeleccionado: number | null;
  onSeleccionarCanton: (cantonId: number | null) => void;
  /** Solo se muestra cuando el usuario está viendo OIJ. */
  activo: boolean;
}

const PANEL: React.CSSProperties = {
  position: "absolute",
  top: "1rem",
  right: "1rem",
  zIndex: 1000,
  background: "white",
  padding: "0.9rem",
  borderRadius: 8,
  boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
  width: "23rem",
  maxHeight: "80vh",
  overflowY: "auto",
  fontSize: "0.85rem",
};

const GRIS = "#64748b";

export default function PanelSeguridadCanton({
  cantonSeleccionado,
  onSeleccionarCanton,
  activo,
}: PanelProps) {
  const [todos, setTodos] = useState<FactorSeguridad[]>([]);
  const [advertencia, setAdvertencia] = useState<string | null>(null);
  const [estadisticas, setEstadisticas] = useState<EstadisticaSeguridad[]>([]);
  const [cargandoEstadisticas, setCargandoEstadisticas] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // El desglose de los 84 cantones se pide una sola vez: son 84 filas de
  // números, y así el panel responde al instante a cada clic — mismo
  // criterio que los paneles de SNIT, SICOP y OSM.
  useEffect(() => {
    obtenerFactorSeguridad()
      .then((resp) => {
        setTodos(resp.datos);
        setAdvertencia(resp.advertencia);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error desconocido"));
  }, []);

  const detalle = useMemo(
    () => todos.find((c) => c.canton_id === cantonSeleccionado) ?? null,
    [todos, cantonSeleccionado],
  );

  // Las estadísticas crudas (por tipo de delito y año) sí se piden por
  // cantón: son varios cientos en todo el país y solo se necesitan las del
  // que está abierto.
  useEffect(() => {
    if (!detalle || detalle.total_delitos === 0) {
      setEstadisticas([]);
      return;
    }

    let cancelado = false;
    setCargandoEstadisticas(true);
    setError(null);

    obtenerEstadisticasPorCanton(detalle.canton_id)
      .then((resp) => {
        if (!cancelado) setEstadisticas(resp.datos);
      })
      .catch((e) => {
        if (!cancelado) setError(e instanceof Error ? e.message : "Error desconocido");
      })
      .finally(() => {
        if (!cancelado) setCargandoEstadisticas(false);
      });

    // Descarta una respuesta lenta si el usuario ya cambió de cantón.
    return () => {
      cancelado = true;
    };
  }, [detalle]);

  const porTipoDelito = useMemo(
    () => [...estadisticas].sort((a, b) => b.cantidad - a.cantidad),
    [estadisticas],
  );

  if (!activo) return null;

  // El error se muestra aunque no haya cantón seleccionado: si la vista
  // v_factor_seguridad todavía no existe, la API responde 503 con el
  // comando que falta correr — mismo criterio que los otros tres paneles.
  if (!detalle) {
    return error ? (
      <div style={PANEL}>
        <h3 style={{ margin: "0 0 0.4rem" }}>Factor de Seguridad (OIJ)</h3>
        <p style={{ color: "#b91c1c", margin: 0 }}>{error}</p>
      </div>
    ) : null;
  }

  return (
    <div style={PANEL}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <h3 style={{ margin: 0 }}>
          {detalle.nombre}
          <span style={{ fontWeight: 400, color: GRIS }}> · {detalle.provincia}</span>
        </h3>
        <button
          onClick={() => onSeleccionarCanton(null)}
          title="Cerrar"
          style={{ border: "none", background: "none", cursor: "pointer", fontSize: "1.1rem" }}
        >
          ✕
        </button>
      </div>

      <p style={{ margin: "0.3rem 0 0.7rem" }}>
        Factor de Seguridad <strong>{Number(detalle.factor_seguridad).toFixed(1)}</strong>
        {" · "}
        {detalle.total_delitos} {detalle.total_delitos === 1 ? "incidente registrado" : "incidentes registrados"}
        {detalle.poblacion ? (
          <>
            {" · "}
            {formatearTasa(Number(detalle.tasa_incidencia))} por cada 10 000 hab.
          </>
        ) : (
          <>
            {" · "}
            <span style={{ color: GRIS }}>sin población cargada, no se pudo calcular tasa</span>
          </>
        )}
      </p>

      {detalle.total_delitos === 0 ? (
        // Un cantón sin incidentes cargados no es un dato faltante: puede
        // ser que de verdad no tenga nada reportado en el rango cargado, o
        // que falte correr el ETL (sync_oij.py) con su archivo del OIJ.
        <p style={{ color: GRIS, margin: 0 }}>
          Sin estadísticas del OIJ cargadas para este cantón en el rango consultado. El Factor
          de Seguridad queda en {Number(detalle.factor_seguridad).toFixed(1)} mientras tanto —
          no implica ausencia real de delitos, solo ausencia de dato cargado.
        </p>
      ) : (
        <>
          {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

          {cargandoEstadisticas ? (
            <p style={{ color: GRIS }}>Cargando estadísticas…</p>
          ) : (
            <div style={{ marginTop: "0.6rem" }}>
              <h4 style={{ margin: "0 0 0.3rem", color: COLOR_ACENTO }}>
                Incidentes por tipo de delito ({porTipoDelito.length})
              </h4>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <tbody>
                  {porTipoDelito.map((fila) => (
                    <tr key={fila.estadistica_id} style={{ borderTop: "1px solid #e2e8f0" }}>
                      <td style={{ padding: "0.25rem 0" }}>
                        {fila.tipo_delito}
                        <span style={{ color: GRIS, fontSize: "0.72rem" }}> · {fila.anio}</span>
                      </td>
                      <td
                        style={{
                          padding: "0.25rem 0 0.25rem 0.4rem",
                          textAlign: "right",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {fila.cantidad}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <p style={{ color: GRIS, marginTop: "0.7rem", fontSize: "0.75rem" }}>
        Fuente: Poder Judicial / OIJ — estadísticas policiales agregadas por cantón. El Factor de
        Seguridad es el inverso de la tasa de incidencia (por 10 000 habitantes) normalizada
        contra los otros 83 cantones, con y sin datos: 100 es el que tiene menor incidencia
        relativa, 0 el que tiene mayor — no es un indicador oficial.
      </p>
      {advertencia && (
        <p
          style={{
            color: COLOR_ACENTO,
            marginTop: "0.5rem",
            fontSize: "0.75rem",
            fontWeight: 600,
            borderTop: "1px solid #fecaca",
            paddingTop: "0.5rem",
          }}
        >
          ⚠ {advertencia}
        </p>
      )}
    </div>
  );
}
