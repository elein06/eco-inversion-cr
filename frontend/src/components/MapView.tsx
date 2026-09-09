import { GeoJSON, MapContainer, Pane, TileLayer } from "react-leaflet";
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
        Base sin nombres: con el tile estándar de OSM los nombres de cantón
        y de lugar vienen dibujados dentro del mismo mosaico, así que
        cualquier capa semitransparente encima (el relleno del índice, las
        capas del SNIT, los puntos de OSM) los tapa sin remedio. Acá se usa
        una base "sin etiquetas" y más abajo se agrega una segunda capa,
        solo con los nombres, en un pane por encima de todo lo demás.

        Se usa Esri (World Light Gray Base/Reference) en vez de CARTO: CARTO
        empezó a pedir API key para sus basemaps y sin ella solo devuelve un
        tile con la marca de agua "API KEY REQUIRED". El par de Esri es
        gratuito sin necesidad de cuenta ni llave, y ya viene pensado para
        este mismo truco (base + capa de referencia con los nombres).
      */}
      <TileLayer
        attribution="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
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
      {mostrarCapasSnit && <CapasAmbientales cantonSeleccionado={cantonSeleccionado} />}
      {mostrarInfraestructuraOsm && (
        <PuntosInfraestructura cantonSeleccionado={cantonSeleccionado} />
      )}
      {/*
        Pane con z-index por encima de overlayPane (400, donde viven los
        rellenos de cantón, las capas del SNIT y los puntos de OSM): así
        los nombres quedan siempre arriba, sin importar qué tan oscuro sea
        el color debajo. `pointerEvents: "none"` para que los clics sigan
        llegando a los cantones y no los tape esta capa (no tiene nada
        clickeable, son solo etiquetas de texto).
      */}
      <Pane name="etiquetas-mapa" style={{ zIndex: 450, pointerEvents: "none" }}>
        <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}" />
      </Pane>
    </MapContainer>
  );
}
