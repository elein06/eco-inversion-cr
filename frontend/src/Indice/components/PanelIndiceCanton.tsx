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
import { semaforoPorIndice } from "../../semaforo";
import { formatearColones, FUENTE_POR_FACTOR, NOMBRE_FACTOR } from "../estilos";

interface PanelIndiceCantonProps {
  cantonSeleccionado: number | null;
  indicesPorCanton: Map<number, IndiceViabilidad>;
  onSeleccionarCanton: (cantonId: number | null) => void;
  /** Solo se muestra cuando el usuario está viendo/ordenando por el Índice total. */
  activo: boolean;
}

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

  // Sin cantón seleccionado (o filtro no activo) no hay nada que mostrar:
  // antes había un panel "vacío" con instrucciones, pero tapaba el mapa
  // sin necesidad cuando todavía no se eligió ningún cantón.
  if (!activo || !cantonSeleccionado || !indice) return null;

  const semaforo = semaforoPorIndice(indice.indice_total);

  const pesos = indice.pesos_usados;
  const formula = [
    `${((pesos.ambiental ?? 0) * 100).toFixed(0)}% × ${indice.factor_ambiental.toFixed(1)} (${NOMBRE_FACTOR.ambiental})`,
    `${((pesos.inversion ?? 0) * 100).toFixed(0)}% × ${indice.factor_inversion.toFixed(1)} (${NOMBRE_FACTOR.inversion})`,
    `${((pesos.conectividad ?? 0) * 100).toFixed(0)}% × ${indice.factor_conectividad.toFixed(1)} (${NOMBRE_FACTOR.conectividad})`,
    `${((pesos.seguridad ?? 0) * 100).toFixed(0)}% × ${indice.factor_seguridad.toFixed(1)} (${NOMBRE_FACTOR.seguridad})`,
  ].join(" + ");

  return (
    <div className="panel-flotante">
      <div className="panel-header">
        <h3>
          {indice.nombre_canton}
          <span className="panel-subt"> · Índice de Viabilidad</span>
        </h3>
        <button
          className="panel-cerrar"
          onClick={() => onSeleccionarCanton(null)}
          title="Cerrar"
        >
          ✕
        </button>
      </div>

      {/*
        Semáforo: el color y la etiqueta cambian solos según el número
        (verde ≥ 70, amarillo ≥ 40, rojo < 40 — ver semaforo.ts). Vive solo
        acá, no en el mapa.
      */}
      <div
        className="semaforo-tarjeta"
        style={{ background: semaforo.colorFondo, borderColor: semaforo.color }}
      >
        <span className="semaforo-punto" style={{ background: semaforo.color }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
            <span className="semaforo-numero" style={{ color: semaforo.colorTexto }}>
              {indice.indice_total.toFixed(1)}
            </span>
            <span
              className="semaforo-pildora"
              style={{ background: semaforo.color, color: "#ffffff" }}
            >
              {semaforo.etiqueta}
            </span>
          </div>
          <div className="formula-indice" style={{ color: semaforo.colorTexto, marginTop: "0.3rem" }}>
            = {formula}
          </div>
        </div>
      </div>

      {indice.advertencia && <p className="advertencia">{indice.advertencia}</p>}

      <h4 className="panel-seccion-titulo">Resumen por fuente OSINT</h4>
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

      <p className="panel-nota">
        Las cuatro fuentes se consumen en vivo (SNIT vía WFS, SICOP vía reportes de
        contratación, OSM vía Overpass API, y el Poder Judicial vía Datos Abiertos): este panel
        es el único lugar que las combina en un solo número, con la fórmula, el semáforo y los
        pesos siempre a la vista.
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
    <li className="panel-lista-item" style={{ alignItems: "flex-start", flexDirection: "column", gap: "0.15rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", width: "100%", fontSize: "0.8rem" }}>
        <strong>
          {fuente} <span style={{ fontWeight: 400, color: "var(--color-texto-suave)" }}>· {etiqueta}</span>
        </strong>
        <span>{valor.toFixed(1)}</span>
      </div>
      <div style={{ color: "var(--color-texto-suave)", fontSize: "0.75rem" }}>{detalle}</div>
    </li>
  );
}
