/**
 * Formato de colones y nombre de la fuente OSINT que alimenta cada factor —
 * usado por el panel del Índice total, que es el único lugar que combina
 * las cuatro fuentes (SNIT, SICOP, OSM, OIJ) en un solo resumen.
 */
const COLONES = new Intl.NumberFormat("es-CR", {
  style: "currency",
  currency: "CRC",
  maximumFractionDigits: 0,
});

export function formatearColones(monto: number): string {
  return COLONES.format(monto);
}

export type ClaveFactor = "ambiental" | "inversion" | "conectividad" | "seguridad";

/** Nombre corto del factor, para la fórmula y los encabezados del resumen. */
export const NOMBRE_FACTOR: Record<ClaveFactor, string> = {
  ambiental: "Ambiental",
  inversion: "Inversión",
  conectividad: "Conectividad",
  seguridad: "Seguridad",
};

/** Fuente OSINT real detrás de cada factor — lo que la rúbrica pide destacar. */
export const FUENTE_POR_FACTOR: Record<ClaveFactor, string> = {
  ambiental: "SNIT",
  inversion: "SICOP",
  conectividad: "OSM",
  seguridad: "OIJ",
};
