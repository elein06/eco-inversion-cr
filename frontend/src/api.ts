import { INDICES_MOCK, ZONAS_MOCK } from "./mock";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
