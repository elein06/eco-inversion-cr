import { useEffect } from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import type { Layer } from "leaflet";
import type { IndiceViabilidad, Zona } from "../api";
import CapasAmbientales from "../SNIT/components/CapasAmbientales";
import { registrarMapa } from "../SNIT/mapa";
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
 * Centra y acerca el mapa al cantón seleccionado, con animación.
 *
 * `cantonSeleccionado` es un solo estado compartido en App.tsx: lo cambian
 * por igual un clic en el sidebar, un clic directo sobre el mapa y
 * cualquiera de los cuatro paneles de detalle (SNIT/SICOP/OSM/OIJ) cuando
 * el usuario elige otro cantón desde ahí. Por eso alcanza con un solo
 * efecto acá, adentro del mapa: no hace falta repetir la lógica de
 * "enfocar" en cada panel por separado, ya enfoca sin importar de dónde
 * vino el clic.
 *
 * De paso, acá también se registra la instancia del mapa en SNIT/mapa.ts
 * (`registrarMapa`). Antes eso solo pasaba dentro de CapasAmbientales, que
 * solo se monta cuando la pestaña activa es SNIT — si el usuario entraba
 * directo a otra pestaña (OSM, por ejemplo) sin pasar antes por SNIT, el
 * mapa quedaba sin registrar y "Ver en el mapa" no hacía nada al hacer
 * clic. Este componente sí está montado siempre, sin importar la pestaña.
 */
function EnfoqueCanton({
  zonas,
  cantonSeleccionado,
}: {
  zonas: Zona[];
  cantonSeleccionado: number | null;
}) {
  const mapa = useMap();

  useEffect(() => {
    registrarMapa(mapa);
  }, [mapa]);

  useEffect(() => {
    if (!cantonSeleccionado) return;
    const zona = zonas.find((z) => z.canton_id === cantonSeleccionado);
    if (!zona) return;

    const limites = L.geoJSON(zona.geom as GeoJSON.GeoJsonObject).getBounds();
    if (!limites.isValid()) return;

    // flyToBounds anima el paneo y el zoom juntos (en vez de saltar de
    // golpe), igual que resaltarGeometria en SNIT/mapa.ts.
    mapa.flyToBounds(limites, { padding: [60, 60], maxZoom: 12, duration: 0.8 });
  }, [cantonSeleccionado, zonas, mapa]);

  return null;
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
      <EnfoqueCanton zonas={zonas} cantonSeleccionado={cantonSeleccionado} />
    </MapContainer>
  );
}
