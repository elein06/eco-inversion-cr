import { useEffect, useMemo, useState } from "react";
import {
  obtenerContratosPorCanton,
  obtenerFactorInversion,
  type ContratoAmbiental,
  type FactorInversion,
} from "../../api";
import { estiloCategoria, formatearColones, PESOS_FACTOR, TOTAL_CATEGORIAS } from "../estilos";

interface PanelProps {
  cantonSeleccionado: number | null;
  onSeleccionarCanton: (cantonId: number | null) => void;
  /** Solo se muestra cuando el usuario está viendo SICOP. */
  activo: boolean;
}

const GRIS = "var(--color-texto-suave)";

export default function PanelInversionCanton({
  cantonSeleccionado,
  onSeleccionarCanton,
  activo,
}: PanelProps) {
  const [todos, setTodos] = useState<FactorInversion[]>([]);
  const [contratos, setContratos] = useState<ContratoAmbiental[]>([]);
  const [cargandoContratos, setCargandoContratos] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // El desglose de los 84 cantones se pide una sola vez: son 84 filas de
  // números, y así el panel responde al instante a cada clic.
  useEffect(() => {
    obtenerFactorInversion()
      .then(setTodos)
      .catch((e) => setError(e instanceof Error ? e.message : "Error desconocido"));
  }, []);

  const detalle = useMemo(
    () => todos.find((c) => c.canton_id === cantonSeleccionado) ?? null,
    [todos, cantonSeleccionado],
  );

  // Los contratos sí se piden por cantón: son miles en todo el país y solo se
  // necesitan los del que está abierto.
  useEffect(() => {
    if (!detalle || detalle.contratos === 0) {
      setContratos([]);
      return;
    }

    let cancelado = false;
    setCargandoContratos(true);
    setError(null);

    obtenerContratosPorCanton(detalle.canton_id)
      .then((filas) => {
        if (!cancelado) setContratos(filas);
      })
      .catch((e) => {
        if (!cancelado) setError(e instanceof Error ? e.message : "Error desconocido");
      })
      .finally(() => {
        if (!cancelado) setCargandoContratos(false);
      });

    // Descarta una respuesta lenta si el usuario ya cambió de cantón.
    return () => {
      cancelado = true;
    };
  }, [detalle]);

  if (!activo) return null;

  // El error se muestra aunque no haya cantón seleccionado: si la vista
  // v_factor_inversion todavía no existe, la API responde 503 con el comando
  // que falta correr, y ese texto es más útil que un "Error 503" pelado.
  if (!detalle) {
    return error ? (
      <div className="panel-flotante">
        <h3 style={{ marginBottom: "0.4rem" }}>Factor de Inversión (SICOP)</h3>
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
        Factor de Inversión <strong>{Number(detalle.factor_inversion).toFixed(1)}</strong>
        {" · "}
        {detalle.contratos} {detalle.contratos === 1 ? "contrato" : "contratos"}
        {" · "}
        {formatearColones(Number(detalle.monto_total))}
      </p>

      {detalle.contratos === 0 ? (
        // Un cantón sin contratos no es un dato faltante: es que no hubo
        // inversión municipal ambiental en el rango consultado.
        <p style={{ color: GRIS, margin: 0 }}>
          Sin contratos ambientales de gobierno local en el rango cargado. El factor queda en
          0 por ausencia de inversión, no por falta de dato.
        </p>
      ) : (
        <>
          <SubPuntaje etiqueta="Monto (50%)" valor={Number(detalle.sub_monto)} />
          <SubPuntaje etiqueta="Cantidad (30%)" valor={Number(detalle.sub_cantidad)} />
          <SubPuntaje etiqueta="Diversidad (20%)" valor={Number(detalle.sub_diversidad)} />

          <p style={{ color: GRIS, margin: "0.6rem 0 0", fontSize: "0.75rem" }}>
            Monto y cantidad son percentiles contra los otros 83 cantones; diversidad es
            cuántas de las {TOTAL_CATEGORIAS} categorías aparecen ({detalle.categorias} acá).
            {detalle.base_monto === "monto_por_habitante"
              ? " El monto se normalizó por habitante."
              : " El monto va en absoluto: este cantón no tiene población cargada."}
          </p>

          {detalle.contratos_otra_moneda > 0 && (
            <p style={{ color: "#b45309", margin: "0.5rem 0 0", fontSize: "0.75rem" }}>
              {detalle.contratos_otra_moneda}{" "}
              {detalle.contratos_otra_moneda === 1 ? "contrato quedó" : "contratos quedaron"} en
              otra moneda y no se suman al monto: SICOP no trajo tipo de cambio.
            </p>
          )}

          {error && <p className="panel-error">{error}</p>}

          {cargandoContratos ? (
            <p style={{ color: GRIS }}>Cargando contratos…</p>
          ) : (
            <TablaContratos filas={contratos} />
          )}
        </>
      )}

      <p className="panel-nota">
        Fuente: SICOP — reportes de carteles, contratos e instituciones. La clasificación
        ambiental es por palabras clave y los pesos ({PESOS_FACTOR}) son decisión del equipo,
        no un indicador oficial. Solo cuenta gobiernos locales.
      </p>
    </div>
  );
}

function SubPuntaje({ etiqueta, valor }: { etiqueta: string; valor: number }) {
  return (
    <div className="subpuntaje">
      <div className="subpuntaje-fila">
        <span>{etiqueta}</span>
        <span>{valor.toFixed(0)}</span>
      </div>
      <div className="subpuntaje-fondo">
        <div className="subpuntaje-relleno" style={{ width: `${Math.min(valor, 100)}%` }} />
      </div>
    </div>
  );
}

function TablaContratos({ filas }: { filas: ContratoAmbiental[] }) {
  // Agrupados por categoría, que es justo lo que mide el sub-puntaje de
  // diversidad: así se ve de qué tipo de inversión se trata.
  const porCategoria = useMemo(() => {
    const mapa = new Map<string, ContratoAmbiental[]>();
    for (const fila of filas) {
      const lista = mapa.get(fila.categoria_detectada) ?? [];
      lista.push(fila);
      mapa.set(fila.categoria_detectada, lista);
    }
    return [...mapa.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [filas]);

  if (filas.length === 0) return null;

  return (
    <div style={{ marginTop: "0.7rem" }}>
      {porCategoria.map(([categoria, contratosCategoria]) => {
        const { color, etiqueta } = estiloCategoria(categoria);
        return (
          <div key={categoria} style={{ marginTop: "0.6rem" }}>
            <h4 className="panel-seccion-titulo" style={{ color, margin: "0 0 0.35rem" }}>
              {etiqueta} ({contratosCategoria.length})
            </h4>
            <table className="panel-tabla" style={{ tableLayout: "fixed" }}>
              <tbody>
                {contratosCategoria.map((contrato) => (
                  <tr key={contrato.contrato_id} className="panel-fila-tabla">
                    <td style={{ padding: "0.3rem 0", overflowWrap: "break-word" }}>
                      {contrato.descripcion_objeto ?? "Sin descripción"}
                      <div style={{ color: GRIS, fontSize: "0.72rem" }}>
                        {contrato.institucion}
                        {contrato.fecha_contrato ? ` · ${contrato.fecha_contrato}` : ""}
                      </div>
                    </td>
                    <td
                      style={{
                        width: "7.5rem",
                        padding: "0.3rem 0 0.3rem 0.4rem",
                        color: GRIS,
                        textAlign: "right",
                        whiteSpace: "nowrap",
                        verticalAlign: "top",
                      }}
                    >
                      {contrato.moneda === "CRC"
                        ? formatearColones(Number(contrato.monto))
                        : `${Number(contrato.monto).toLocaleString("es-CR")} ${contrato.moneda}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}
