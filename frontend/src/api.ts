import { INDICES_MOCK, ZONAS_MOCK } from "./mock";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";


export type TipoCapa = "area_protegida" | "corredor_biologico" | "hidrografia";

export interface CapaSnit {
  capa_id: number;
  tipo_capa: TipoCapa;
  nombre: string | null;
  atributos: Record<string, unknown>;
  fecha_consulta: string;
  geom: GeoJSON.Geometry;
}

export interface FactorAmbiental {
  canton_id: number;
  codigo_ine: string;
  nombre: string;
  provincia: string;
  area_km2: number;
  pct_area_protegida: number;
  pct_corredor_biologico: number;
  densidad_drenaje_km_km2: number;
  sub_asp: number;
  sub_corredor: number;
  sub_hidro: number;
  factor_ambiental: number;
}

export interface ResumenCapa {
  tipo_capa: TipoCapa;
  total: number;
  ultima_consulta: string;
}


export async function obtenerCapasSnit(
  tipo: TipoCapa,
  cantonId?: number | null,
  limite = 500,
): Promise<CapaSnit[]> {
  const parametros = new URLSearchParams({ tipo, limite: String(limite) });
  if (cantonId) parametros.set("canton_id", String(cantonId));
  return obtenerJson<CapaSnit[]>(`/ambiental/capas?${parametros}`);
}


export interface Zona {
  canton_id: number;
  codigo_ine: string;
  nombre: string;
  provincia: string;
  poblacion: number | null;
  geom: GeoJSON.Geometry;
}

export interface IndiceViabilidad {
  canton_id: number;
  nombre_canton: string;
  factor_ambiental: number;
  factor_inversion: number;
  factor_conectividad: number;
  factor_seguridad: number;
  indice_total: number;
  pesos_usados: Record<string, number>;
  fecha_calculo: string;
  advertencia?: string;
}

/** Desglose del Factor Ambiental por cantón (vista v_factor_ambiental). */
export async function obtenerFactorAmbiental(): Promise<FactorAmbiental[]> {
  return obtenerJson<FactorAmbiental[]>("/ambiental/factor");
}


export async function obtenerResumenCapasSnit(): Promise<ResumenCapa[]> {
  return obtenerJson<ResumenCapa[]>("/ambiental/capas/resumen");
}
async function obtenerJson<T>(ruta: string): Promise<T> {
  const respuesta = await fetch(`${API_BASE_URL}${ruta}`);
  if (!respuesta.ok) {
    throw new Error(`Error ${respuesta.status} al consultar ${ruta}`);
  }
  return respuesta.json() as Promise<T>;
}

/** Cae a datos de prueba si la API real todavía no está disponible (ver mock.ts). */
export async function obtenerZonas(): Promise<{ datos: Zona[]; esMock: boolean }> {
  try {
    return { datos: await obtenerJson<Zona[]>("/zonas"), esMock: false };
  } catch {
    return { datos: ZONAS_MOCK, esMock: true };
  }
}

export async function obtenerIndices(): Promise<{ datos: IndiceViabilidad[]; esMock: boolean }> {
  try {
    return { datos: await obtenerJson<IndiceViabilidad[]>("/indice-viabilidad"), esMock: false };
  } catch {
    return { datos: INDICES_MOCK, esMock: true };
  }
}

async function obtenerJsonConDetalle<T>(ruta: string): Promise<T> {
  const respuesta = await fetch(`${API_BASE_URL}${ruta}`);
  if (!respuesta.ok) {
    let mensaje = `Error ${respuesta.status}`;
    try {
      const cuerpo = await respuesta.json();
      if (cuerpo?.detail) mensaje = String(cuerpo.detail);
    } catch {
      // Respuesta sin JSON: se queda el mensaje genérico.
    }
    throw new Error(mensaje);
  }
  return respuesta.json() as Promise<T>;
}

/** Capas de un cantón buscado por nombre (la API ignora tildes y mayúsculas). */
export async function obtenerCapasPorCanton(
  tipo: TipoCapa,
  canton: string,
  limite = 200,
): Promise<CapaSnit[]> {
  const parametros = new URLSearchParams({ tipo, canton, limite: String(limite) });
  return obtenerJsonConDetalle<CapaSnit[]>(`/ambiental/capas?${parametros}`);
}

/** Factor Ambiental de un cantón buscado por nombre. */
export async function obtenerFactorPorCanton(canton: string): Promise<FactorAmbiental[]> {
  const parametros = new URLSearchParams({ canton });
  return obtenerJsonConDetalle<FactorAmbiental[]>(`/ambiental/factor?${parametros}`);
}

/* ------------------------------------------------------------------ */
/* SICOP — Integrante 2                                               */
/* ------------------------------------------------------------------ */

/** Cómo se normalizó el monto antes de rankearlo (columna `base_monto`). */
export type BaseMonto = "monto_por_habitante" | "monto_absoluto";

export interface FactorInversion {
  canton_id: number;
  codigo_ine: string;
  nombre: string;
  provincia: string;
  contratos: number;
  contratos_otra_moneda: number;
  monto_total: number;
  categorias: number;
  base_monto: BaseMonto;
  sub_monto: number;
  sub_cantidad: number;
  sub_diversidad: number;
  factor_inversion: number;
}

export interface ContratoAmbiental {
  contrato_id: number;
  canton_id: number | null;
  institucion: string;
  municipalidad: string | null;
  monto: number;
  moneda: string;
  fecha_contrato: string | null;
  descripcion_objeto: string | null;
  categoria_detectada: string;
}

/**
 * Desglose del Factor de Inversión de los 84 cantones (vista
 * v_factor_inversion). Usa `obtenerJsonConDetalle` a propósito: si el ETL
 * todavía no corrió `--calcular-factor`, la API responde 503 con el comando
 * que falta, y ese texto es más útil que un "Error 503" pelado.
 */
export async function obtenerFactorInversion(): Promise<FactorInversion[]> {
  return obtenerJsonConDetalle<FactorInversion[]>("/inversion/factor");
}

/** Contratos ambientales de un cantón (los que alimentan su factor). */
export async function obtenerContratosPorCanton(cantonId: number): Promise<ContratoAmbiental[]> {
  return obtenerJsonConDetalle<ContratoAmbiental[]>(`/contratos-ambientales?canton_id=${cantonId}`);
}

/* ------------------------------------------------------------------ */
/* OSM / Overpass — Integrante 3                                      */
/* ------------------------------------------------------------------ */

/** Coincide con las claves de `CATEGORIAS_OSM` en `etl/osm/sync_osm.py`. */
export type CategoriaOsm = "centro_acopio" | "escuela" | "via_principal";

export interface InfraestructuraOsm {
  poi_id: number;
  canton_id: number | null;
  categoria: CategoriaOsm;
  nombre: string | null;
  geom: GeoJSON.Point;
  fecha_consulta: string;
  valido_hasta: string;
}

/**
 * Puntos de interés de OSM/Overpass de un cantón (fuente: Integrante 3):
 * centros de acopio, escuelas y vías principales. Por defecto solo trae los
 * vigentes (dentro de la caché de OSM_CACHE_DIAS días), que es justo lo que
 * el backend cuenta para el Factor de Conectividad.
 */
export async function obtenerInfraestructuraPorCanton(
  cantonId: number,
  soloVigente = true,
): Promise<InfraestructuraOsm[]> {
  const parametros = new URLSearchParams({
    canton_id: String(cantonId),
    solo_vigente: String(soloVigente),
  });
  return obtenerJsonConDetalle<InfraestructuraOsm[]>(`/infraestructura?${parametros}`);
}

export interface FactorConectividad {
  canton_id: number;
  codigo_ine: string;
  nombre: string;
  provincia: string;
  pois_centro_acopio: number;
  pois_escuela: number;
  pois_via_principal: number;
  total_pois: number;
  factor_conectividad: number;
}

/**
 * Desglose del Factor de Conectividad de los 84 cantones (vista
 * v_factor_conectividad). Usa `obtenerJsonConDetalle` a propósito: si el ETL
 * todavía no corrió `--calcular-factor`, la API responde 503 con el comando
 * que falta correr, igual que `/inversion/factor` de SICOP.
 */
export async function obtenerFactorConectividad(): Promise<FactorConectividad[]> {
  return obtenerJsonConDetalle<FactorConectividad[]>("/infraestructura/factor");
}

/* ------------------------------------------------------------------ */
/* OIJ / Poder Judicial — Integrante 4                                */
/* ------------------------------------------------------------------ */

/** Respuesta de los endpoints de /seguridad: siempre trae la advertencia ética junto a los datos. */
export interface RespuestaSeguridad<T> {
  advertencia: string;
  datos: T;
}

export interface EstadisticaSeguridad {
  estadistica_id: number;
  canton_id: number;
  tipo_delito: string;
  cantidad: number;
  anio: number;
  fecha_consulta: string;
}

export interface FactorSeguridad {
  canton_id: number;
  codigo_ine: string;
  nombre: string;
  provincia: string;
  poblacion: number | null;
  total_delitos: number;
  tasa_incidencia: number;
  factor_seguridad: number;
}

/**
 * Desglose del Factor de Seguridad de los 84 cantones (vista
 * v_factor_seguridad). Usa `obtenerJsonConDetalle` a propósito: si el ETL
 * todavía no corrió `--calcular-factor`, la API responde 503 con el comando
 * que falta correr, igual que /inversion/factor e /infraestructura/factor.
 * La advertencia ética viaja en la misma respuesta — nunca hardcodeada acá.
 */
export async function obtenerFactorSeguridad(): Promise<RespuestaSeguridad<FactorSeguridad[]>> {
  return obtenerJsonConDetalle<RespuestaSeguridad<FactorSeguridad[]>>("/seguridad/factor");
}

/** Estadísticas policiales crudas (por tipo de delito y año) de un cantón. */
export async function obtenerEstadisticasPorCanton(
  cantonId: number,
): Promise<RespuestaSeguridad<EstadisticaSeguridad[]>> {
  const parametros = new URLSearchParams({ canton_id: String(cantonId) });
  return obtenerJsonConDetalle<RespuestaSeguridad<EstadisticaSeguridad[]>>(`/seguridad?${parametros}`);
}
