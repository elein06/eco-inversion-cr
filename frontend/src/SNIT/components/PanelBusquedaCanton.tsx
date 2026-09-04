
import { useEffect, useMemo, useState } from "react";
import {
  obtenerCapasPorCanton,
  obtenerFactorAmbiental,
  type CapaSnit,
  type FactorAmbiental,
} from "../../api";
import { ESTILOS } from "../estilos";

interface PanelProps {
  cantonSeleccionado: number | null;
  onSeleccionarCanton: (cantonId: number | null) => void;
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

export default function PanelBusquedaCanton({
  cantonSeleccionado,
  onSeleccionarCanton,
}: PanelProps) {
  const [todos, setTodos] = useState<FactorAmbiental[]>([]);
  const [areas, setAreas] = useState<CapaSnit[]>([]);
  const [corredores, setCorredores] = useState<CapaSnit[]>([]);
  const [cargandoCapas, setCargandoCapas] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // El Factor Ambiental de los 84 cantones se pide una sola vez: son datos
  // livianos y así el panel responde al instante a cada clic.
  useEffect(() => {
    obtenerFactorAmbiental()
      .then(setTodos)
      .catch((e) => setError(e instanceof Error ? e.message : "Error desconocido"));
  }, []);

  const detalle = useMemo(
    () => todos.find((c) => c.canton_id === cantonSeleccionado) ?? null,
    [todos, cantonSeleccionado],
  );

  // Las capas sí se piden a la API en cada selección: filtrarlas en el
  // navegador obligaría a descargar las 6 656 geometrías del país.
  useEffect(() => {
    if (!detalle) {
      setAreas([]);
      setCorredores([]);
      return;
    }

    let cancelado = false;
    setCargandoCapas(true);
    setError(null);

    Promise.all([
      obtenerCapasPorCanton("area_protegida", detalle.nombre),
      obtenerCapasPorCanton("corredor_biologico", detalle.nombre),
    ])
      .then(([a, c]) => {
        if (cancelado) return;
        setAreas(a);
        setCorredores(c);
      })
      .catch((e) => {
        if (!cancelado) setError(e instanceof Error ? e.message : "Error desconocido");
      })
      .finally(() => {
        if (!cancelado) setCargandoCapas(false);
      });

    // Descarta una respuesta lenta si el usuario ya cambió de cantón.
    return () => {
      cancelado = true;
    };
  }, [detalle]);

  // Sin cantón seleccionado el panel no existe: no estorba el mapa.
  if (!detalle) return null;

  return (
    <div style={PANEL}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <h3 style={{ margin: 0 }}>
          {detalle.nombre}
          <span style={{ fontWeight: 400, color: "#64748b" }}> · {detalle.provincia}</span>
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
        Factor Ambiental <strong>{Number(detalle.factor_ambiental).toFixed(1)}</strong>
        {" · "}
        {Number(detalle.pct_area_protegida).toFixed(1)}% protegido
        {" · "}
        {Number(detalle.pct_corredor_biologico).toFixed(1)}% en corredor
      </p>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      {cargandoCapas ? (
        <p style={{ color: "#64748b" }}>Cargando capas…</p>
      ) : (
        <>
          <Tabla
            titulo="Áreas silvestres protegidas"
            color={ESTILOS.area_protegida.color}
            filas={areas}
            campoDetalle="cat_manejo"
          />
          <Tabla
            titulo="Corredores biológicos"
            color={ESTILOS.corredor_biologico.color}
            filas={corredores}
            campoDetalle="regmplan"
          />
        </>
      )}

      <p style={{ color: "#64748b", marginTop: "0.7rem", fontSize: "0.75rem" }}>
        Fuente: SNIT — nodos SINAC e IGN, consumidos por WFS.
      </p>
    </div>
  );
}

function Tabla({
  titulo,
  color,
  filas,
  campoDetalle,
}: {
  titulo: string;
  color: string;
  filas: CapaSnit[];
  campoDetalle: string;
}) {
  return (
    <div style={{ marginTop: "0.7rem" }}>
      <h4 style={{ margin: "0 0 0.3rem", color }}>
        {titulo} ({filas.length})
      </h4>
      {filas.length === 0 ? (
        <p style={{ margin: 0, color: "#64748b" }}>Ninguno en este cantón.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            {filas.map((fila) => (
              <tr key={fila.capa_id} style={{ borderTop: "1px solid #e2e8f0" }}>
                <td style={{ padding: "0.25rem 0" }}>{fila.nombre ?? "Sin nombre"}</td>
                <td style={{ padding: "0.25rem 0", color: "#64748b", textAlign: "right" }}>
                  {String(fila.atributos?.[campoDetalle] ?? "")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
