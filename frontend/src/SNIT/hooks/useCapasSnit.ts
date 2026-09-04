
import { useEffect, useState } from "react";
import { obtenerCapasSnit, type CapaSnit, type TipoCapa } from "../../api";
import { LIMITES, ORDEN_CAPAS } from "../estilos";

export interface EstadoCapasSnit {
  capas: Record<TipoCapa, CapaSnit[]>;
  cargando: boolean;
  error: string | null;
}

const CAPAS_VACIAS: Record<TipoCapa, CapaSnit[]> = {
  area_protegida: [],
  corredor_biologico: [],
  hidrografia: [],
};

export function useCapasSnit(cantonSeleccionado: number | null): EstadoCapasSnit {
  const [capas, setCapas] = useState<Record<TipoCapa, CapaSnit[]>>(CAPAS_VACIAS);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Si el usuario cambia de cantón antes de que llegue la respuesta anterior,
    // esta bandera descarta la vieja para que no pise a la nueva.
    let cancelado = false;

    async function cargar() {
      setCargando(true);
      try {
        const resultados = await Promise.all(
          ORDEN_CAPAS.map((tipo) =>
            obtenerCapasSnit(tipo, cantonSeleccionado, LIMITES[tipo]),
          ),
        );
        if (cancelado) return;

        const nuevas = { ...CAPAS_VACIAS };
        ORDEN_CAPAS.forEach((tipo, indice) => {
          nuevas[tipo] = resultados[indice];
        });
        setCapas(nuevas);
        setError(null);
      } catch (e) {
        // Falla clara pero no destructiva: el mapa sigue mostrando los
        // cantones aunque estas capas no carguen.
        if (!cancelado) {
          setError(e instanceof Error ? e.message : "Error desconocido");
          setCapas(CAPAS_VACIAS);
        }
      } finally {
        if (!cancelado) setCargando(false);
      }
    }

    cargar();
    return () => {
      cancelado = true;
    };
  }, [cantonSeleccionado]);

  return { capas, cargando, error };
}