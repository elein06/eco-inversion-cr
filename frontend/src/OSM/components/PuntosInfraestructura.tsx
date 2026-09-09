import { CircleMarker, LayerGroup, Popup } from "react-leaflet";
import { estiloCategoria } from "../estilos";
import { useInfraestructuraOsm } from "../hooks/useInfraestructuraOsm";

interface PuntosInfraestructuraProps {
  /** Solo se dibuja para el cantón elegido: sin eso habría que traer los
   * POIs del país entero, que es justo lo que la caché de 7 días busca
   * evitar consultar de más. */
  cantonSeleccionado: number | null;
}

/** Extrae [lat, lon] de un Point GeoJSON; ignora geometrías que no sean puntos. */
function coordenadas(geom: GeoJSON.Geometry): [number, number] | null {
  if (geom.type !== "Point") return null;
  const [lon, lat] = geom.coordinates;
  return [lat, lon];
}

export default function PuntosInfraestructura({ cantonSeleccionado }: PuntosInfraestructuraProps) {
  const { pois, error } = useInfraestructuraOsm(cantonSeleccionado);

  if (error) {
    // Igual que CapasAmbientales: una capa que no carga no debe tumbar el
    // mapa completo, solo queda sin dibujar.
    console.warn("No se pudo cargar la infraestructura de OSM:", error);
    return null;
  }

  if (pois.length === 0) return null;

  return (
    <LayerGroup>
      {pois.map((poi) => {
        const coords = coordenadas(poi.geom);
        if (!coords) return null;
        const { color, etiqueta } = estiloCategoria(poi.categoria);
        return (
          <CircleMarker
            key={poi.poi_id}
            center={coords}
            radius={6}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 1 }}
          >
            <Popup>
              <strong>{poi.nombre ?? "Sin nombre"}</strong>
              <br />
              {etiqueta}
            </Popup>
          </CircleMarker>
        );
      })}
    </LayerGroup>
  );
}
