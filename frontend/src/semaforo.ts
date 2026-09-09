/**
 * Semáforo del Índice de Viabilidad para el panel del Índice total.
 *
 * Usa EXACTAMENTE los mismos 4 cortes y colores que `colorPorIndice` en
 * `components/MapView.tsx` (70 / 50 / 35), a propósito: así el color que
 * ves en el mapa y el color que ves en el panel siempre coinciden para el
 * mismo cantón. Si algún día cambian los cortes del mapa, hay que
 * replicarlos acá también — no hay una sola fuente de verdad porque
 * MapView no importa de fuera de sí mismo (ver nota ahí).
 */
export type NivelSemaforo = "alto" | "medio" | "medio_bajo" | "bajo";

export interface Semaforo {
  nivel: NivelSemaforo;
  etiqueta: string;
  color: string;
  colorTexto: string;
  colorFondo: string;
}

export function semaforoPorIndice(valor: number): Semaforo {
  if (valor >= 70) {
    return {
      nivel: "alto",
      etiqueta: "Alto",
      color: "#16a34a",
      colorTexto: "#15803d",
      colorFondo: "#dcfce7",
    };
  }
  if (valor >= 50) {
    return {
      nivel: "medio",
      etiqueta: "Medio",
      color: "#eab308",
      colorTexto: "#a16207",
      colorFondo: "#fef9c3",
    };
  }
  if (valor >= 35) {
    return {
      nivel: "medio_bajo",
      etiqueta: "Medio-bajo",
      color: "#f97316",
      colorTexto: "#c2410c",
      colorFondo: "#ffedd5",
    };
  }
  return {
    nivel: "bajo",
    etiqueta: "Bajo",
    color: "#dc2626",
    colorTexto: "#b91c1c",
    colorFondo: "#fee2e2",
  };
}
