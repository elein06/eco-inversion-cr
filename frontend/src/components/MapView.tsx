import { GeoJSON, MapContainer, TileLayer } from "react-leaflet";
import type { Layer } from "leaflet";
import type { IndiceViabilidad, Zona } from "../api";
import CapasAmbientales from "../SNIT/components/CapasAmbientales";
import PuntosInfraestructura from "../OSM/components/PuntosInfraestructura";
interface MapViewProps {
  zonas: Zona[];
  indicesPorCanton: Map<number, IndiceViabilidad>;
  cantonSeleccionado: number | null;
  onSeleccionarCanton: (cantonId: number) => void;
  mostrarCapasSnit?: boolean;
  mostrarInfraestructuraOsm?: boolean;
}

/**
 * Verde (alto) → amarillo → naranja → rojo (bajo), acorde al índice_total
 * de cada cantón. Mismos cortes que `semaforoPorIndice` en `semaforo.ts`
 * (70 / 50 / 35) — se repiten acá a propósito, ver la nota en ese archivo.
 */
function colorPorIndice(indice: number | undefined): string {
  if (indice === undefined) return "#9ca3af"; // gris: sin datos aún
  if (indice >= 70) return "#16a34a";
  if (indice >= 50) return "#eab308";
  if (indice >= 35) return "#f97316";
  return "#dc2626";
}

export default function MapView({
  zonas,
  indicesPorCanton,
  cantonSeleccionado,
  onSeleccionarCanton,
  mostrarCapasSnit = false,
  mostrarInfraestructuraOsm = false,
}: MapViewProps) {
  return (
    <MapContainer center={[9.93, -84.08]} zoom={8} style={{ height: "100%", width: "100%" }}>
      {/*
        Tile estándar de OSM: es el que trae el azul del mar y el relieve/
        detalle de color por defecto. Antes se había cambiado por una base
        "sin etiquetas" (CARTO, después Esri) para poder poner los nombres
        en una capa aparte por encima del relleno de color — pero esas
        bases son planas/grises a propósito, y perdían todo ese detalle.
        El nombre de cada cantón ya no depende del tile: se agrega como
        tooltip de Leaflet (ver onEachFeature más abajo), que por defecto
        vive en el tooltipPane (z-index 650) — por encima del overlayPane
        (400) donde está el relleno de color — así que queda visible sin
        tener que sacrificar el mapa base.
      */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
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
            onEachFeature={(_feature, layer: Layer) => {
              layer.bindTooltip(zona.nombre, {
                permanent: true,
                direction: "center",
                className: "etiqueta-canton",
              });
            }}
          />
        );
      })}
      {mostrarCapasSnit && <CapasAmbientales cantonSeleccionado={cantonSeleccionado} />}
      {mostrarInfraestructuraOsm && (
        <PuntosInfraestructura cantonSeleccionado={cantonSeleccionado} />
      )}
    </MapContainer>
  );
}
