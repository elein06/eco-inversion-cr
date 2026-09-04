import { useEffect, useMemo, useState } from "react";
import { obtenerIndices, obtenerZonas, type IndiceViabilidad, type Zona } from "./api";
import MapView from "./components/MapView";
import Sidebar from "./components/Sidebar";
import PanelBusquedaCanton from "./SNIT/components/PanelBusquedaCanton";
type CriterioOrden = "indice_total" | "factor_ambiental" | "factor_inversion" | "factor_conectividad" | "factor_seguridad";

export default function App() {
  const [zonas, setZonas] = useState<Zona[]>([]);
  const [indices, setIndices] = useState<IndiceViabilidad[]>([]);
  const [usandoMock, setUsandoMock] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [criterioOrden, setCriterioOrden] = useState<CriterioOrden>("indice_total");
  const [cantonSeleccionado, setCantonSeleccionado] = useState<number | null>(null);

  useEffect(() => {
    async function cargarDatos() {
      const [resZonas, resIndices] = await Promise.all([obtenerZonas(), obtenerIndices()]);
      setZonas(resZonas.datos);
      setIndices(resIndices.datos);
      setUsandoMock(resZonas.esMock || resIndices.esMock);
      setCargando(false);
    }
    cargarDatos();
  }, []);

  const indicesPorCanton = useMemo(
    () => new Map(indices.map((indice) => [indice.canton_id, indice])),
    [indices],
  );

  if (cargando) {
    return <div className="cargando">Cargando datos de Eco-Inversión Costa Rica…</div>;
  }

  return (
    <div className="app">
      {usandoMock && (
        <div className="banner-mock">
          Mostrando datos de prueba (mock) — la API real todavía no responde en{" "}
          {import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}
        </div>
      )}
      <div className="app-body">
        <Sidebar
          indices={indices}
          criterioOrden={criterioOrden}
          onCambiarCriterio={setCriterioOrden}
          cantonSeleccionado={cantonSeleccionado}
          onSeleccionarCanton={setCantonSeleccionado}
        />
        <main className="mapa-contenedor">
          <MapView
            zonas={zonas}
            indicesPorCanton={indicesPorCanton}
            cantonSeleccionado={cantonSeleccionado}
            onSeleccionarCanton={setCantonSeleccionado}
          />
          <PanelBusquedaCanton
            cantonSeleccionado={cantonSeleccionado}
            onSeleccionarCanton={setCantonSeleccionado}
          />
        </main>
      </div>
    </div>
  );
}
