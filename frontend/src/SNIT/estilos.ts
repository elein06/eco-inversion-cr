
import type { TipoCapa } from "../api";

export interface EstiloCapa {
  color: string;
  etiqueta: string;
  /** Las líneas de hidrografía no se rellenan, solo se trazan. */
  relleno: boolean;
  /** Si arranca visible al abrir el mapa. */
  visiblePorDefecto: boolean;
}

export const ESTILOS: Record<TipoCapa, EstiloCapa> = {
  area_protegida: {
    color: "#15803d",
    etiqueta: "Áreas protegidas (SINAC)",
    relleno: true,
    visiblePorDefecto: true,
  },
  corredor_biologico: {
    color: "#7c3aed",
    etiqueta: "Corredores biológicos (SINAC)",
    relleno: true,
    visiblePorDefecto: true,
  },
  hidrografia: {
    color: "#2563eb",
    etiqueta: "Hidrografía (IGN)",
    relleno: false,
    // Arranca apagada: son cientos de líneas y tapan el resto del mapa.
    visiblePorDefecto: false,
  },
};


export const LIMITES: Record<TipoCapa, number> = {
  area_protegida: 200,
  corredor_biologico: 200,
  hidrografia: 400,
};

/** Orden en que se listan las capas en el control del mapa. */
export const ORDEN_CAPAS: TipoCapa[] = [
  "area_protegida",
  "corredor_biologico",
  "hidrografia",
];