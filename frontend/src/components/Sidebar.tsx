import { useEffect, useRef, useState } from "react";
import type { IndiceViabilidad } from "../api";
import { semaforoPorIndice } from "../semaforo";

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

/**
 * Reemplaza el <select> nativo: mismo comportamiento (un valor elegido de
 * una lista fija), pero con un menú que sí se puede estilizar igual que el
 * resto de la app — el navegador no deja tocar el look del menú nativo.
 */
function SelectorCriterio({
  valor,
  onCambiar,
}: {
  valor: CriterioOrden;
  onCambiar: (criterio: CriterioOrden) => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const contenedorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;

    function alClickFuera(e: MouseEvent) {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false);
      }
    }
    function alTecla(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }

    document.addEventListener("mousedown", alClickFuera);
    document.addEventListener("keydown", alTecla);
    return () => {
      document.removeEventListener("mousedown", alClickFuera);
      document.removeEventListener("keydown", alTecla);
    };
  }, [abierto]);

  return (
    <div className="selector-moderno" ref={contenedorRef}>
      <button
        type="button"
        className={`selector-boton ${abierto ? "abierto" : ""}`}
        onClick={() => setAbierto((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={abierto}
        aria-label="Ordenar por"
      >
        <span>{ETIQUETAS_CRITERIO[valor]}</span>
        <span className={`selector-flecha ${abierto ? "abierta" : ""}`} aria-hidden>
          ▾
        </span>
      </button>
      {abierto && (
        <ul className="selector-menu" role="listbox">
          {Object.entries(ETIQUETAS_CRITERIO).map(([clave, etiqueta]) => (
            <li
              key={clave}
              role="option"
              aria-selected={clave === valor}
              className={`selector-opcion ${clave === valor ? "activa" : ""}`}
              onClick={() => {
                onCambiar(clave as CriterioOrden);
                setAbierto(false);
              }}
            >
              <span className="selector-punto" aria-hidden />
              {etiqueta}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

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
  // De mayor a menor por defecto: al cambiar el criterio (p. ej. a SNIT),
  // el que tiene el valor más alto en ESE factor queda arriba. La
  // dirección es independiente del criterio y no se resetea al cambiarlo
  // — así el botón de invertir se respeta aunque el usuario después
  // cambie de "Ordenar por".
  const [direccion, setDireccion] = useState<"desc" | "asc">("desc");

  const ordenados = [...indices].sort((a, b) =>
    direccion === "desc"
      ? b[criterioOrden] - a[criterioOrden]
      : a[criterioOrden] - b[criterioOrden],
  );
  const seleccionado = indices.find((i) => i.canton_id === cantonSeleccionado);
  const ordenandoPorFactor = criterioOrden !== "indice_total";

  return (
    <aside className="sidebar">
      <h1>Eco-Inversión Costa Rica</h1>
      <p className="subtitulo">Índice de Viabilidad por cantón</p>

      <div className="filtro">
        <span>Ordenar por</span>
        <div className="filtro-controles">
          <SelectorCriterio valor={criterioOrden} onCambiar={onCambiarCriterio} />
          <button
            type="button"
            className="boton-direccion"
            onClick={() => setDireccion((d) => (d === "desc" ? "asc" : "desc"))}
            title={
              direccion === "desc"
                ? "De mayor a menor — clic para invertir"
                : "De menor a mayor — clic para invertir"
            }
            aria-label="Invertir orden de la lista"
          >
            {direccion === "desc" ? "↓" : "↑"}
          </button>
        </div>
      </div>

      <ul className="lista-cantones">
        {ordenados.map((indice) => {
          // El punto de color siempre refleja el índice total (no el
          // factor por el que se está ordenando): es la salud general del
          // cantón, de un vistazo, sin tener que abrir el detalle.
          const semaforo = semaforoPorIndice(indice.indice_total);
          return (
            <li
              key={indice.canton_id}
              className={indice.canton_id === cantonSeleccionado ? "activo" : ""}
              onClick={() => onSeleccionarCanton(indice.canton_id)}
            >
              <span className="fila-canton">
                <span
                  className="punto-semaforo"
                  style={{ background: semaforo.color }}
                  title={`Índice total: ${semaforo.etiqueta.toLowerCase()}`}
                />
                <span>{indice.nombre_canton}</span>
              </span>
              {/*
                El número que se muestra es el del criterio por el que se está
                ordenando. Si siempre fuera `indice_total`, ordenar por un factor
                dejaría la lista viéndose desordenada, porque el orden vendría de
                un valor que no está a la vista. Cuando el criterio no es el
                índice total, este se sigue mostrando al lado, en gris.
              */}
              <span className="valores-canton">
                <strong>{indice[criterioOrden].toFixed(1)}</strong>
                {ordenandoPorFactor && (
                  <span className="valor-secundario" title="Índice total">
                    {indice.indice_total.toFixed(1)}
                  </span>
                )}
              </span>
            </li>
          );
        })}
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
