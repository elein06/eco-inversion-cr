/**
 * Estilos y constantes del panel de OIJ (Integrante 4).
 *
 * A diferencia de OSM (3 categorías fijas) o SICOP (categorías detectadas
 * por palabra clave, también fijas), el tipo de delito en los datos del OIJ
 * es texto libre que viene del CSV real (ROBO, HURTO, ESTAFA...) y puede
 * variar según lo que traiga cada carga. Por eso no hay un mapa fijo
 * categoría → color como en las otras fuentes: se usa un único color de
 * acento (rojo/naranja, temática de seguridad) para todo el panel.
 */
export const COLOR_ACENTO = "#b91c1c";

/** Formatea la tasa de incidencia por 10,000 habitantes con un decimal. */
export function formatearTasa(tasa: number): string {
  return tasa.toLocaleString("es-CR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}
