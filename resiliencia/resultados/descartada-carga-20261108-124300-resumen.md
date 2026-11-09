# Experimento de carga con corte de la base

Reporte: `carga-20261108-124300.json`

## Línea de tiempo

```
2026-11-08T12:43:01  +  0.0s  inicio de la carga (base normal)
2026-11-08T12:43:21  + 20.0s  CORTE: proxy deshabilitado, la API no alcanza a PostgreSQL
2026-11-08T12:43:41  + 40.0s  RESTAURADO: proxy habilitado de nuevo
```

## Respuestas por ventana de 10 s

| Ventana | 200 | 503 | Errores de red/timeout | p95 ms | máx ms |
|---|---|---|---|---|---|
|    0–10 s | 0 | 60 | 0 | 29.1 | 40 |
|   10–20 s | 0 | 100 | 0 | 32.8 | 95 |
|   20–30 s | 89 | 10 | 0 | 153 | 299 |
|   30–40 s | 100 | 0 | 0 | 138.4 | 169 |
|   40–50 s | 101 | 0 | 0 | 144 | 210 |
|   50–60 s | 100 | 0 | 0 | 82.3 | 131 |
|   60–70 s | 40 | 0 | 0 | 45.2 | 75 |

Total: 600 solicitudes, 430 con 200, 170 con 503.

Las ventanas son de Artillery y no coinciden exactamente con los segundos
del corte; compárelas con la línea de tiempo.
