
import { GeoJSON, LayersControl } from "react-leaflet";
import type { TipoCapa } from "../../api";
import { ESTILOS, ORDEN_CAPAS } from "../estilos";
import { useCapasSnit } from "../hooks/useCapasSnit";

interface CapasAmbientalesProps {
  /** Si hay un cantón seleccionado, las capas se filtran a esa zona. */
  cantonSeleccionado: number | null;
}

export default function CapasAmbientales({ cantonSeleccionado }: CapasAmbientalesProps) {
  const { capas, error } = useCapasSnit(cantonSeleccionado);

  if (error) {
    console.warn("No se pudieron cargar las capas del SNIT:", error);
    return null;
  }

  return (
    <LayersControl position="topright">
      {ORDEN_CAPAS.map((tipo: TipoCapa) => {
        const estilo = ESTILOS[tipo];
        return (
          <LayersControl.Overlay
            key={tipo}
            name={`${estilo.etiqueta} (${capas[tipo].length})`}
            checked={estilo.visiblePorDefecto}
          >
            <GeoJSON
              // La `key` incluye el cantón y la cantidad: sin eso, Leaflet
              // reusaría la capa anterior y el mapa no se actualizaría al
              // seleccionar otro cantón.
              key={`${tipo}-${cantonSeleccionado ?? "pais"}-${capas[tipo].length}`}
              data={
                {
                  type: "FeatureCollection",
                  features: capas[tipo].map((capa) => ({
                    type: "Feature" as const,
                    geometry: capa.geom,
                    properties: { nombre: capa.nombre, ...capa.atributos },
                  })),
                } as GeoJSON.GeoJsonObject
              }
              style={{
                color: estilo.color,
                weight: estilo.relleno ? 2 : 1.5,
                fillColor: estilo.color,
                fillOpacity: estilo.relleno ? 0.35 : 0,
              }}
              onEachFeature={(feature, layer) => {
                const props = feature.properties ?? {};
                const detalle = props.cat_manejo ?? props.regmplan ?? props.categoria ?? "";
                layer.bindPopup(
                  `<strong>${props.nombre ?? "Sin nombre"}</strong><br/>` +
                    `${estilo.etiqueta}${detalle ? `<br/>${detalle}` : ""}`,
                );
              }}
            />
          </LayersControl.Overlay>
        );
      })}
    </LayersControl>
  );
}