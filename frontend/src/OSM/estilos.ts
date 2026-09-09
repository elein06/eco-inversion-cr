import type { CategoriaOsm } from "../api";

export interface EstiloCategoriaOsm {
  color: string;
  etiqueta: string;
}

/**
 * Color y etiqueta por categoría de infraestructura. Las claves son
 * exactamente los valores de `CATEGORIAS_OSM` en `etl/osm/sync_osm.py`, que
 * es lo que el ETL guarda en `infraestructura_osm.categoria`.
 */
export const CATEGORIAS: Record<CategoriaOsm, EstiloCategoriaOsm> = {
  centro_acopio: { color: "#059669", etiqueta: "Centros de acopio" },
  escuela: { color: "#2563eb", etiqueta: "Escuelas" },
  via_principal: { color: "#ea580c", etiqueta: "Vías principales" },
};

/** Orden en que se listan las categorías en el panel y en el mapa. */
export const ORDEN_CATEGORIAS: CategoriaOsm[] = ["centro_acopio", "escuela", "via_principal"];

/** Cae a gris si el ETL llegara a guardar una categoría que el panel no conoce. */
export function estiloCategoria(categoria: string): EstiloCategoriaOsm {
  return (
    (CATEGORIAS as Record<string, EstiloCategoriaOsm>)[categoria] ?? {
      color: "#64748b",
      etiqueta: categoria,
    }
  );
}

/**
 * Días de vigencia de la caché de Overpass. Coincide con el valor por
 * defecto de OSM_CACHE_DIAS en .env.example — es solo para el texto
 * explicativo del panel, no cambia qué trae la API (eso lo decide el
 * backend con `valido_hasta`, filtrado server-side).
 */
export const CACHE_DIAS_DEFECTO = 7;
