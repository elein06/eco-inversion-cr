import { useEffect, useState } from "react";
import { obtenerInfraestructuraPorCanton, type InfraestructuraOsm } from "../../api";

export interface EstadoInfraestructuraOsm {
  pois: InfraestructuraOsm[];
  cargando: boolean;
  error: string | null;
}

/**
 * Puntos de interés de OSM (fuente: Integrante 3) de un cantón. Se piden a
 * la API en cada selección, igual que las capas del SNIT y los contratos de
 * SICOP: son los únicos que hacen falta, no los de los 84 cantones.
 */
export function useInfraestructuraOsm(cantonSeleccionado: number | null): EstadoInfraestructuraOsm {
  const [pois, setPois] = useState<InfraestructuraOsm[]>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cantonSeleccionado == null) {
      setPois([]);
      setError(null);
      return;
    }

    // Si el usuario cambia de cantón antes de que llegue la respuesta
    // anterior, esta bandera descarta la vieja para que no pise a la nueva.
    let cancelado = false;
    setCargando(true);
    setError(null);

    obtenerInfraestructuraPorCanton(cantonSeleccionado)
      .then((filas) => {
        if (!cancelado) setPois(filas);
      })
      .catch((e) => {
        if (!cancelado) setError(e instanceof Error ? e.message : "Error desconocido");
      })
      .finally(() => {
        if (!cancelado) setCargando(false);
      });

    return () => {
      cancelado = true;
    };
  }, [cantonSeleccionado]);

  return { pois, cargando, error };
}
