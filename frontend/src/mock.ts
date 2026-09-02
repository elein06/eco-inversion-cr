/**
 * Datos de prueba para que el frontend avance sin esperar a que las cuatro
 * fuentes estén cargadas en la base de datos (ver plan de trabajo, semana 1).
 * Se usan como respaldo automático si la API real (VITE_API_BASE_URL) no responde.
 */
import type { IndiceViabilidad, Zona } from "./api";

export const ZONAS_MOCK: Zona[] = [
  {
    canton_id: 1,
    codigo_ine: "1-01",
    nombre: "San José",
    provincia: "San José",
    poblacion: 342188,
    geom: {
      type: "Polygon",
      coordinates: [
        [
          [-84.12, 9.9],
          [-84.06, 9.9],
          [-84.06, 9.95],
          [-84.12, 9.95],
          [-84.12, 9.9],
        ],
      ],
    },
  },
  {
    canton_id: 2,
    codigo_ine: "2-01",
    nombre: "Alajuela",
    provincia: "Alajuela",
    poblacion: 254440,
    geom: {
      type: "Polygon",
      coordinates: [
        [
          [-84.25, 10.0],
          [-84.18, 10.0],
          [-84.18, 10.05],
          [-84.25, 10.05],
          [-84.25, 10.0],
        ],
      ],
    },
  },
  {
    canton_id: 3,
    codigo_ine: "7-01",
    nombre: "Limón",
    provincia: "Limón",
    poblacion: 108988,
    geom: {
      type: "Polygon",
      coordinates: [
        [
          [-83.05, 9.98],
          [-82.98, 9.98],
          [-82.98, 10.03],
          [-83.05, 10.03],
          [-83.05, 9.98],
        ],
      ],
    },
  },
];

export const INDICES_MOCK: IndiceViabilidad[] = [
  {
    canton_id: 2,
    nombre_canton: "Alajuela",
    factor_ambiental: 78,
    factor_inversion: 62,
    factor_conectividad: 70,
    factor_seguridad: 65,
    indice_total: 68.75,
    pesos_usados: { ambiental: 0.25, inversion: 0.25, conectividad: 0.25, seguridad: 0.25 },
    fecha_calculo: new Date().toISOString(),
  },
  {
    canton_id: 3,
    nombre_canton: "Limón",
    factor_ambiental: 85,
    factor_inversion: 40,
    factor_conectividad: 35,
    factor_seguridad: 45,
    indice_total: 51.25,
    pesos_usados: { ambiental: 0.25, inversion: 0.25, conectividad: 0.25, seguridad: 0.25 },
    fecha_calculo: new Date().toISOString(),
  },
  {
    canton_id: 1,
    nombre_canton: "San José",
    factor_ambiental: 30,
    factor_inversion: 80,
    factor_conectividad: 90,
    factor_seguridad: 40,
    indice_total: 60.0,
    pesos_usados: { ambiental: 0.25, inversion: 0.25, conectividad: 0.25, seguridad: 0.25 },
    fecha_calculo: new Date().toISOString(),
  },
];
