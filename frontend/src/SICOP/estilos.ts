/**
 * Color y etiqueta por categoría ambiental. Las claves son exactamente las de
 * `PALABRAS_CLAVE_AMBIENTAL` en `etl/sicop/sync_sicop.py`, que es lo que el
 * ETL guarda en `contratos_ambientales.categoria_detectada`.
 */
export const CATEGORIAS: Record<string, { color: string; etiqueta: string }> = {
  residuos: { color: "#b45309", etiqueta: "Residuos" },
  reciclaje: { color: "#0d9488", etiqueta: "Reciclaje" },
  agua: { color: "#2563eb", etiqueta: "Agua y saneamiento" },
  areas_verdes: { color: "#15803d", etiqueta: "Áreas verdes" },
  infraestructura_verde: { color: "#7c3aed", etiqueta: "Infraestructura verde" },
  gestion_ambiental: { color: "#ca8a04", etiqueta: "Gestión ambiental" },
};

/** Total de categorías posibles: es el denominador de `sub_diversidad`. */
export const TOTAL_CATEGORIAS = Object.keys(CATEGORIAS).length;

/** Cae a gris si el ETL llegara a detectar una categoría que el panel no conoce. */
export function estiloCategoria(categoria: string) {
  return CATEGORIAS[categoria] ?? { color: "#64748b", etiqueta: categoria };
}

const COLONES = new Intl.NumberFormat("es-CR", {
  style: "currency",
  currency: "CRC",
  maximumFractionDigits: 0,
});

export function formatearColones(monto: number): string {
  return COLONES.format(monto);
}

/** Pesos internos del factor — decisión del equipo, documentada en docs/sicop.md. */
export const PESOS_FACTOR = "50% monto · 30% cantidad · 20% diversidad";
