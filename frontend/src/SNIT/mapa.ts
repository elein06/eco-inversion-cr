/**
 * Control del mapa de Leaflet desde fuera del <MapContainer> — Integrante 1.
 *
 * El panel de detalle vive fuera del mapa, así que no puede usar el hook
 * `useMap()` de react-leaflet. `CapasAmbientales` sí está adentro, y por eso
 * registra acá la instancia apenas se monta; el panel la usa para acercarse a
 * una geometría y resaltarla cuando el usuario hace clic en la tabla.
 *
 * Es un módulo suelto y no un contexto de React a propósito: así todo se
 * resuelve dentro de la carpeta SNIT, sin agregar un proveedor en App.tsx, que
 * es archivo compartido del equipo.
 */
import L from "leaflet";
import type { LayerGroup, Map as MapaLeaflet } from "leaflet";

let mapa: MapaLeaflet | null = null;

/** Capa del resaltado actual, para poder borrarla antes de dibujar otra. */
let resaltado: LayerGroup | null = null;

export function registrarMapa(instancia: MapaLeaflet): void {
  mapa = instancia;
}

export function obtenerMapa(): MapaLeaflet | null {
  return mapa;
}

/** Evita que un nombre con < o & rompa el HTML del globo. */
function escapar(texto: string): string {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

/** Borra el resaltado anterior, si lo hay. */
export function limpiarResaltado(): void {
  if (mapa && resaltado) {
    mapa.removeLayer(resaltado);
  }
  resaltado = null;
}

/**
 * Acerca el mapa a una geometría del SNIT y la marca, como hace un buscador de
 * direcciones: contorno ámbar sobre la capa original, un punto en el centro y
 * un globo con el nombre.
 *
 * Los límites se calculan con L.geoJSON en vez de guardarlos en la base: la
 * geometría ya viaja en la respuesta, así que sacar su rectángulo envolvente
 * sale gratis y evita una consulta más.
 */
export function resaltarGeometria(
  geom: GeoJSON.Geometry,
  nombre: string,
  detalle?: string,
): void {
  if (!mapa) return;

  limpiarResaltado();

  const contorno = L.geoJSON(geom, {
    style: {
      color: "#b45309",
      weight: 4,
      fillColor: "#f59e0b",
      fillOpacity: 0.35,
      // La línea discontinua distingue el resaltado de las capas de fondo,
      // que son continuas.
      dashArray: "6 4",
    },
  });

  const limites = contorno.getBounds();
  if (!limites.isValid()) return;

  // Se usa circleMarker y no marker porque el icono por defecto de Leaflet
  // apunta a imágenes que los empaquetadores no resuelven solos.
  const punto = L.circleMarker(limites.getCenter(), {
    radius: 9,
    color: "#b45309",
    weight: 3,
    fillColor: "#fbbf24",
    fillOpacity: 0.95,
  });

  punto.bindPopup(
    `<strong>${escapar(nombre)}</strong>` +
      (detalle ? `<br/>${escapar(detalle)}` : ""),
  );

  resaltado = L.layerGroup([contorno, punto]).addTo(mapa);

  // maxZoom evita que una geometría chica deje el mapa pegado al suelo, sin
  // contexto alrededor.
  mapa.fitBounds(limites, { padding: [60, 60], maxZoom: 12 });
  punto.openPopup();
}
