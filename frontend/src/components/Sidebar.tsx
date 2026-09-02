import type { IndiceViabilidad } from "../api";

type CriterioOrden = "indice_total" | "factor_ambiental" | "factor_inversion" | "factor_conectividad" | "factor_seguridad";

interface SidebarProps {
  indices: IndiceViabilidad[];
  criterioOrden: CriterioOrden;
  onCambiarCriterio: (criterio: CriterioOrden) => void;
  cantonSeleccionado: number | null;
  onSeleccionarCanton: (cantonId: number) => void;
}

const ETIQUETAS_CRITERIO: Record<CriterioOrden, string> = {
  indice_total: "Índice total",
  factor_ambiental: "Factor ambiental (SNIT)",
  factor_inversion: "Factor de inversión (SICOP)",
  factor_conectividad: "Factor de conectividad (OSM)",
  factor_seguridad: "Factor de seguridad (OIJ)",
};

function Barra({ etiqueta, valor }: { etiqueta: string; valor: number }) {
  return (
    <div className="barra">
      <div className="barra-etiqueta">
        <span>{etiqueta}</span>
        <span>{valor.toFixed(0)}</span>
      </div>
      <div className="barra-fondo">
        <div className="barra-relleno" style={{ width: `${Math.min(valor, 100)}%` }} />
      </div>
    </div>
  );
}

export default function Sidebar({
  indices,
  criterioOrden,
  onCambiarCriterio,
  cantonSeleccionado,
  onSeleccionarCanton,
}: SidebarProps) {
  const ordenados = [...indices].sort((a, b) => b[criterioOrden] - a[criterioOrden]);
  const seleccionado = indices.find((i) => i.canton_id === cantonSeleccionado);

  return (
    <aside className="sidebar">
      <h1>Eco-Inversión Costa Rica</h1>
      <p className="subtitulo">Índice de Viabilidad por cantón</p>

      <label className="filtro">
        Ordenar por
        <select value={criterioOrden} onChange={(e) => onCambiarCriterio(e.target.value as CriterioOrden)}>
          {Object.entries(ETIQUETAS_CRITERIO).map(([valor, etiqueta]) => (
            <option key={valor} value={valor}>
              {etiqueta}
            </option>
          ))}
        </select>
      </label>

      <ul className="lista-cantones">
        {ordenados.map((indice) => (
          <li
            key={indice.canton_id}
            className={indice.canton_id === cantonSeleccionado ? "activo" : ""}
            onClick={() => onSeleccionarCanton(indice.canton_id)}
          >
            <span>{indice.nombre_canton}</span>
            <strong>{indice.indice_total.toFixed(1)}</strong>
          </li>
        ))}
      </ul>

      {seleccionado && (
        <div className="detalle">
          <h2>{seleccionado.nombre_canton}</h2>
          <Barra etiqueta="Ambiental (SNIT)" valor={seleccionado.factor_ambiental} />
          <Barra etiqueta="Inversión (SICOP)" valor={seleccionado.factor_inversion} />
          <Barra etiqueta="Conectividad (OSM)" valor={seleccionado.factor_conectividad} />
          <Barra etiqueta="Seguridad (OIJ)" valor={seleccionado.factor_seguridad} />
          <p className="pesos">
            Pesos usados:{" "}
            {Object.entries(seleccionado.pesos_usados)
              .map(([factor, peso]) => `${factor} ${(peso * 100).toFixed(0)}%`)
              .join(" · ")}
          </p>
          {seleccionado.advertencia && <p className="advertencia">{seleccionado.advertencia}</p>}
        </div>
      )}
    </aside>
  );
}
