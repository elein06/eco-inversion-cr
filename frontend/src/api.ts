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

/** Capas de un cantón buscado por nombre (sin tildes ni mayúsculas). */
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