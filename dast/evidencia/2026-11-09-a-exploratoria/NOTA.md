# Corrida exploratoria (2026-11-09, 14:39)

Primera ejecución del plan, **anterior a dos cambios**, que se conserva porque
de ella salieron esos cambios y el hallazgo H-DAST-03 (ver `docs/dast.md`):

- La base no tenía las vistas `v_factor_*` (las crean los ETL). Las cuatro
  rutas de factores respondían 503/500 antes de usar los parámetros, así que el
  análisis activo no llegaba a sus consultas. Desde entonces
  `ejecutar_dast.py` crea esas vistas con el SQL de los propios ETL.
- El análisis activo no excluía tecnologías ajenas al proyecto y llegó al
  límite de 15 minutos (`Job activeScan finished, time taken: 00:15:00` en
  `zap-salida.txt`). Con las reglas actuales esta corrida se reportaría como
  **INCOMPLETO**, no como aprobada.

Alertas: 3 de riesgo Bajo (90022 y 10023 en `/ambiental/factor`, que respondía
500 por la vista ausente; 10021 `X-Content-Type-Options`) y 3 informativas.
Ninguna de riesgo Medio o Alto. Ejecutada en el workspace Linux de Claude, sin
Docker (modo `--objetivo`), contra el commit `1bceb32`.
