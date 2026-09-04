import { GeoJSON, MapContainer, TileLayer } from "react-leaflet";
import type { IndiceViabilidad, Zona } from "../api";
import CapasAmbientales from "../SNIT/components/CapasAmbientales";
interface MapViewProps {
  zonas: Zona[];
  indicesPorCanton: Map<number, IndiceViabilidad>;
  cantonSeleccionado: number | null;
  onSeleccionarCanton: (cantonId: number) => void;
}

/** Verde (alto) → amarillo → rojo (bajo), acorde al índice_total de cada cantón. */
function colorPorIndice(indice: number | undefined): string {
  if (indice === undefined) return "#9ca3af"; // gris: sin datos aún
  if (indice >= 70) return "#16a34a";
  if (indice >= 50) return "#eab308";
  if (indice >= 30) return "#f97316";
  return "#dc2626";
}

export default function MapView({
  zonas,
  indicesPorCanton,
  cantonSeleccionado,
  onSeleccionarCanton,
}: MapViewProps) {
  return (
    <MapContainer center={[9.93, -84.08]} zoom={8} style={{ height: "100%", width: "100%" }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {zonas.map((zona) => {
        const indice = indicesPorCanton.get(zona.canton_id);
        const esSeleccionado = zona.canton_id === cantonSeleccionado;
        return (
          <GeoJSON
            key={zona.canton_id}
            data={zona.geom as GeoJSON.GeoJsonObject}
            style={{
              color: esSeleccionado ? "#1d4ed8" : "#374151",
              weight: esSeleccionado ? 3 : 1,
              fillColor: colorPorIndice(indice?.indice_total),
              fillOpacity: 0.6,
            }}
            eventHandlers={{
              click: () => onSeleccionarCanton(zona.canton_id),
            }}
          />
        );
      })}
      <CapasAmbientales cantonSeleccionado={cantonSeleccionado} />
    </MapContainer>
  );
}
