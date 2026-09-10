
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
  /** Solo se muestra cuando el usuario está viendo  SNIT. */
  activo: boolean;
}

const GRIS = "var(--color-texto-suave)";

export default function PanelBusquedaCanton({
  cantonSeleccionado,
  onSeleccionarCanton,
  activo,
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
  if (!detalle || !activo) return null;

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
        Factor Ambiental <strong>{Number(detalle.factor_ambiental).toFixed(1)}</strong>
        {" · "}
        {Number(detalle.pct_area_protegida).toFixed(1)}% protegido
        {" · "}
        {Number(detalle.pct_corredor_biologico).toFixed(1)}% en corredor
      </p>

      {error && <p className="panel-error">{error}</p>}

      {cargandoCapas ? (
        <p style={{ color: GRIS }}>Cargando capas…</p>
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

      <p className="panel-nota">Fuente: SNIT — nodos SINAC e IGN, consumidos por WFS.</p>
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
      <h4 className="panel-seccion-titulo" style={{ color, margin: "0 0 0.35rem" }}>
        {titulo} ({filas.length})
      </h4>
      {filas.length === 0 ? (
        <p style={{ margin: 0, color: GRIS }}>Ninguno en este cantón.</p>
      ) : (
        <table className="panel-tabla">
          <tbody>
            {filas.map((fila) => (
              <tr key={fila.capa_id} className="panel-fila-tabla">
                <td style={{ padding: "0.3rem 0" }}>{fila.nombre ?? "Sin nombre"}</td>
                <td style={{ padding: "0.3rem 0", color: GRIS, textAlign: "right" }}>
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
