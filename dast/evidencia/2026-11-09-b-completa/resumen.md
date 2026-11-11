# Resumen DAST (ítem 4.7)

- **Fecha:** 2026-11-09T15:09:58-06:00
- **Commit analizado:** `1bceb32c839af749197f7b9d1cb57955bef9df61`
- **Objetivo:** `http://127.0.0.1:8000` (ambiente aislado, datos ficticios)
- **Plan:** `dast/zap-plan.yaml` (ZAP 2.16.1, Automation Framework)
- **Duración:** 11.1 min
- **Código de salida de ZAP:** 2
- **Resultado:** **APROBADO**
  - Solo alertas de riesgo Bajo: se reportan, no bloquean

## Alertas por riesgo

| Riesgo | Tipos de alerta |
|---|---|
| Alto | 0 |
| Medio | 0 |
| Bajo | 1 |
| Informativo | 3 |

## Detalle

| Riesgo | Id | Alerta | Confianza | Instancias | Ejemplo |
|---|---|---|---|---|---|
| Bajo | 10021 | X-Content-Type-Options Header Missing | 2 | 28 | `http://127.0.0.1:8000` |
| Informativo | 10111 | Authentication Request Identified | 1 | 3 | `http://127.0.0.1:8000/auth/login` |
| Informativo | 10112 | Session Management Response Identified | 3 | 68 | `http://127.0.0.1:8000/auth/login` |
| Informativo | 10104 | User Agent Fuzzer | 2 | 108 | `http://127.0.0.1:8000/ambiental/factor/` |

## Rutas analizadas (34 rutas, 38 URL con parámetros)

Inventario en `rutas-analizadas.txt` (historial de importación OpenAPI, rastreo y
comprobación de sesión). El análisis activo envía además miles de variantes con
cargas de ataque sobre estas rutas; se ven en `api-log.txt`.

| Tipo | Ruta | Variantes en el historial |
|---|---|---|
| con sesión | `/auth/yo` | 1 |
| con sesión | `/escenarios` | 1 |
| con sesión | `/escenarios/` | 1 |
| con sesión | `/escenarios//export.csv` | 1 |
| con sesión | `/escenarios//ranking` | 1 |
| con sesión | `/escenarios/1` | 1 |
| con sesión | `/escenarios/1/export.csv` | 1 |
| con sesión | `/escenarios/1/ranking` | 1 |
| con sesión | `/indice-viabilidad/recalcular` | 1 |
| pública | `/` | 1 |
| pública | `/ambiental/capas` | 1 |
| pública | `/ambiental/capas/resumen` | 1 |
| pública | `/ambiental/factor` | 2 |
| pública | `/ambiental/factor/` | 1 |
| pública | `/auth/login` | 1 |
| pública | `/auth/registro` | 1 |
| pública | `/contratos-ambientales` | 1 |
| pública | `/health` | 1 |
| pública | `/health/listo` | 1 |
| pública | `/indice-viabilidad` | 1 |
| pública | `/infraestructura` | 1 |
| pública | `/infraestructura/factor` | 2 |
| pública | `/infraestructura/factor/` | 1 |
| pública | `/infraestructura/resumen` | 1 |
| pública | `/inversion/factor` | 2 |
| pública | `/inversion/factor/` | 1 |
| pública | `/inversion/resumen` | 1 |
| pública | `/openapi.json` | 1 |
| pública | `/seguridad` | 1 |
| pública | `/seguridad/factor` | 2 |
| pública | `/seguridad/factor/` | 1 |
| pública | `/seguridad/resumen` | 1 |
| pública | `/zonas` | 1 |
| pública | `/zonas/` | 1 |

Archivos: `zap-reporte.html`, `zap-reporte.json`, `zap-salida.txt`, `api-log.txt`.
