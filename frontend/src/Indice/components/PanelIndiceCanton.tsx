import { useEffect, useMemo, useState } from "react";
import {
  obtenerFactorAmbiental,
  obtenerFactorConectividad,
  obtenerFactorInversion,
  obtenerFactorSeguridad,
  type FactorAmbiental,
  type FactorConectividad,
  type FactorInversion,
  type FactorSeguridad,
  type IndiceViabilidad,
} from "../../api";
import { formatearColones, FUENTE_POR_FACTOR, NOMBRE_FACTOR } from "../estilos";

interface PanelIndiceCantonProps {
  cantonSeleccionado: number | null;
  indicesPorCanton: Map<number, IndiceViabilidad>;
  onSeleccionarCanton: (cantonId: number | null) => void;
  /** Solo se muestra cuando el usuario está viendo/ordenando por el Índice total. */
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
  width: "24rem",
  maxHeight: "80vh",
  overflowY: "auto",
  fontSize: "0.85rem",
};

const GRIS = "#64748b";

export default function PanelIndiceCanton({
  cantonSeleccionado,
  indicesPorCanton,
  onSeleccionarCanton,
  activo,
}: PanelIndiceCantonProps) {
  const [ambiental, setAmbiental] = useState<FactorAmbiental[]>([]);
  const [inversion, setInversion] = useState<FactorInversion[]>([]);
  const [conectividad, setConectividad] = useState<FactorConectividad[]>([]);
  const [seguridad, setSeguridad] = useState<FactorSeguridad[]>([]);

  // Igual patrón que los cuatro paneles de factor (SNIT/SICOP/OSM/OIJ): el
  // desglose de los 84 cantones de cada fuente se pide una sola vez al
  // montar, así el resumen responde al instante a cada clic. Si alguna
  // vista todavía no existe (nadie corrió --calcular-factor en esa fuente),
  // esa fuente queda vacía y el resumen lo dice en vez de romper el panel.
  useEffect(() => {
    obtenerFactorAmbiental().then(setAmbiental).catch(() => setAmbiental([]));
    obtenerFactorInversion().then(setInversion).catch(() => setInversion([]));
    obtenerFactorConectividad().then(setConectividad).catch(() => setConectividad([]));
    obtenerFactorSeguridad()
      .then((r) => setSeguridad(r.datos))
      .catch(() => setSeguridad([]));
  }, []);

  const indice = cantonSeleccionado ? indicesPorCanton.get(cantonSeleccionado) : undefined;

  const amb = useMemo(
    () => ambiental.find((f) => f.canton_id === cantonSeleccionado),
    [ambiental, cantonSeleccionado],
  );
  const inv = useMemo(
    () => inversion.find((f) => f.canton_id === cantonSeleccionado),
    [inversion, cantonSeleccionado],
  );
  const con = useMemo(
    () => conectividad.find((f) => f.canton_id === cantonSeleccionado),
    [conectividad, cantonSeleccionado],
  );
  const seg = useMemo(
    () => seguridad.find((f) => f.canton_id === cantonSeleccionado),
    [seguridad, cantonSeleccionado],
  );

  if (!activo) return null;

  // Sin cantón elegido todavía: se muestra un panel liviano en vez de nada,
  // para que quede claro que el resumen existe y cómo activarlo (clave para
  // la demo: el valor de la app se ve al comparar un cantón contra otro).
  if (!cantonSeleccionado || !indice) {
    return (
      <div style={PANEL}>
        <h3 style={{ margin: 0 }}>Índice de Viabilidad</h3>
        <p style={{ color: GRIS, margin: "0.6rem 0 0" }}>
          Hacé clic en un cantón (en el mapa o en la lista) para ver la fórmula exacta del
          índice y el resumen de las cuatro fuentes OSINT que lo componen.
        </p>
      </div>
    );
  }

  const pesos = indice.pesos_usados;
  const formula = [
    `${((pesos.ambiental ?? 0) * 100).toFixed(0)}% × ${indice.factor_ambiental.toFixed(1)} (${NOMBRE_FACTOR.ambiental})`,
    `${((pesos.inversion ?? 0) * 100).toFixed(0)}% × ${indice.factor_inversion.toFixed(1)} (${NOMBRE_FACTOR.inversion})`,
    `${((pesos.conectividad ?? 0) * 100).toFixed(0)}% × ${indice.factor_conectividad.toFixed(1)} (${NOMBRE_FACTOR.conectividad})`,
    `${((pesos.seguridad ?? 0) * 100).toFixed(0)}% × ${indice.factor_seguridad.toFixed(1)} (${NOMBRE_FACTOR.seguridad})`,
  ].join(" + ");

  return (
    <div style={PANEL}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <h3 style={{ margin: 0 }}>
          {indice.nombre_canton}
          <span style={{ fontWeight: 400, color: GRIS }}> · Índice de Viabilidad</span>
        </h3>
        <button
          onClick={() => onSeleccionarCanton(null)}
          title="Cerrar"
          style={{ border: "none", background: "none", cursor: "pointer", fontSize: "1.1rem" }}
        >
          ✕
        </button>
      </div>

      <div
        style={{
          margin: "0.6rem 0",
          padding: "0.6rem 0.7rem",
          background: "#f0fdf4",
          border: "1px solid #bbf7d0",
          borderRadius: 6,
        }}
      >
        <div style={{ fontSize: "1.7rem", fontWeight: 700, color: "#15803d", lineHeight: 1.1 }}>
          {indice.indice_total.toFixed(1)}
        </div>
        <div style={{ fontSize: "0.78rem", color: "#166534", marginTop: "0.25rem" }}>
          = {formula}
        </div>
      </div>

      {indice.advertencia && <p className="advertencia">{indice.advertencia}</p>}

      <h4 style={{ margin: "0.7rem 0 0.3rem" }}>Resumen por fuente OSINT</h4>
      <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
        <FuenteResumen
          fuente={FUENTE_POR_FACTOR.ambiental}
          etiqueta={NOMBRE_FACTOR.ambiental}
          valor={indice.factor_ambiental}
          detalle={
            amb
              ? `${amb.pct_area_protegida.toFixed(1)}% de área protegida · ${amb.pct_corredor_biologico.toFixed(1)}% en corredor biológico · ${amb.densidad_drenaje_km_km2.toFixed(2)} km de drenaje/km²`
              : "sin datos cargados todavía"
          }
        />
        <FuenteResumen
          fuente={FUENTE_POR_FACTOR.inversion}
          etiqueta={NOMBRE_FACTOR.inversion}
          valor={indice.factor_inversion}
          detalle={
            inv
              ? `${inv.contratos} ${inv.contratos === 1 ? "contrato ambiental" : "contratos ambientales"} · ${formatearColones(inv.monto_total)} · ${inv.categorias} ${inv.categorias === 1 ? "categoría" : "categorías"}`
              : "sin datos cargados todavía"
          }
        />
        <FuenteResumen
          fuente={FUENTE_POR_FACTOR.conectividad}
          etiqueta={NOMBRE_FACTOR.conectividad}
          valor={indice.factor_conectividad}
          detalle={
            con
              ? `${con.total_pois} puntos de interés (${con.pois_centro_acopio} centros de acopio · ${con.pois_escuela} escuelas · ${con.pois_via_principal} vías principales)`
              : "sin datos cargados todavía"
          }
        />
        <FuenteResumen
          fuente={FUENTE_POR_FACTOR.seguridad}
          etiqueta={NOMBRE_FACTOR.seguridad}
          valor={indice.factor_seguridad}
          detalle={
            seg
              ? `${seg.total_delitos} ${seg.total_delitos === 1 ? "incidente registrado" : "incidentes registrados"} · tasa de ${seg.tasa_incidencia.toFixed(2)} por 10 000 hab.`
              : "sin datos cargados todavía"
          }
        />
      </ul>

      <p style={{ color: GRIS, marginTop: "0.8rem", fontSize: "0.72rem" }}>
        Las cuatro fuentes se consumen en vivo (SNIT vía WFS, SICOP vía reportes de
        contratación, OSM vía Overpass API, y el Poder Judicial vía Datos Abiertos): este panel
        es el único lugar que las combina en un solo número, con la fórmula y los pesos siempre
        a la vista.
      </p>
    </div>
  );
}

function FuenteResumen({
  fuente,
  etiqueta,
  valor,
  detalle,
}: {
  fuente: string;
  etiqueta: string;
  valor: number;
  detalle: string;
}) {
  return (
    <li style={{ marginTop: "0.55rem", paddingTop: "0.55rem", borderTop: "1px solid #f1f5f9" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem" }}>
        <strong>
          {fuente} <span style={{ fontWeight: 400, color: GRIS }}>· {etiqueta}</span>
        </strong>
        <span>{valor.toFixed(1)}</span>
      </div>
      <div style={{ color: GRIS, fontSize: "0.75rem", marginTop: "0.15rem" }}>{detalle}</div>
    </li>
  );
}
