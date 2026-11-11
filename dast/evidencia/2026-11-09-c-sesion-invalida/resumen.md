# Resumen DAST (ítem 4.7)

- **Fecha:** 2026-11-09T15:14:16-06:00
- **Commit analizado:** `1bceb32c839af749197f7b9d1cb57955bef9df61`
- **Objetivo:** `http://127.0.0.1:8000` (ambiente aislado, datos ficticios)
- **Plan:** `dast/zap-plan.yaml` (ZAP 2.16.1, Automation Framework)
- **Duración:** 0.1 min
- **Código de salida de ZAP:** 1
- **Resultado:** **INCOMPLETO**
  - La comprobación de sesión (requestor) falló

## Alertas por riesgo

| Riesgo | Tipos de alerta |
|---|---|
| Alto | 0 |
| Medio | 0 |
| Bajo | 0 |
| Informativo | 0 |

## Detalle

| Riesgo | Id | Alerta | Confianza | Instancias | Ejemplo |
|---|---|---|---|---|---|

## Rutas analizadas (0 rutas, 0 URL con parámetros)

Inventario en `rutas-analizadas.txt` (historial de importación OpenAPI, rastreo y
comprobación de sesión). El análisis activo envía además miles de variantes con
cargas de ataque sobre estas rutas; se ven en `api-log.txt`.

| Tipo | Ruta | Variantes en el historial |
|---|---|---|

Archivos: `zap-reporte.html`, `zap-reporte.json`, `zap-salida.txt`, `api-log.txt`.
