# Análisis de seguridad (ítems 2.3 y 3.2)

Semgrep CE analiza el código, Gitleaks busca secretos y OSV-Scanner revisa las
dependencias. Las tres herramientas corren en Docker, con imágenes fijadas por
digest en `docker-compose.seguridad.yml`. Ese archivo es la única configuración:
CI ejecuta los mismos servicios que se ejecutan en local.

## Alcance

| Herramienta | Servicio | Analiza | Fuera del alcance |
|---|---|---|---|
| Semgrep CE | `semgrep` | `backend/app`, `etl`, `frontend/src`, Dockerfile, Compose y workflows. Reglas: Python, JavaScript, TypeScript, React, auditoría de seguridad, OWASP Top 10, Dockerfile, Compose, GitHub Actions y la regla propia de `seguridad/reglas-semgrep.yml` | `backend/tests` y `resiliencia/`, que no se despliegan (`.semgrepignore`) |
| Gitleaks | `gitleaks-historial` | Todos los commits de la rama | Archivos sin commit |
| Gitleaks | `gitleaks-archivos` | Archivos actuales, con o sin commit. Solo local y demostración | Historial |
| OSV-Scanner | `osv` | `backend/requirements-dev.lock` (incluye producción) y `frontend/package-lock.json` | ETL: sus `requirements.txt` no fijan versiones |
| OSV-Scanner | `osv-herramientas` | `resiliencia/package-lock.json` (Artillery) | Resultado informativo |

La regla propia `eco-sql-con-datos-de-la-solicitud` existe porque los paquetes
públicos no detectaron inyección SQL en los cursores de psycopg2 que usa la API.
Sigue los parámetros de cada ruta de FastAPI hasta el texto de `execute`. Una
consulta con `%s` y valores aparte no la activa.

## Cómo ejecutarlos

Requiere Docker. Los comandos funcionan igual en PowerShell y Bash, desde la
raíz del repositorio:

```bash
docker compose -f docker-compose.seguridad.yml run --rm semgrep
docker compose -f docker-compose.seguridad.yml run --rm gitleaks-archivos
docker compose -f docker-compose.seguridad.yml run --rm gitleaks-historial
docker compose -f docker-compose.seguridad.yml run --rm osv
```

Antes de hacer commit, `gitleaks-archivos` es el que importa: encuentra el
secreto antes de que entre al historial. Los reportes quedan en
`reportes/seguridad/`, ignorada por Git.

Los contenedores corren con el UID fijo `1001:1001`, sin privilegios: las
imágenes de Semgrep, Gitleaks y OSV-Scanner usan root si no se les indica otro
usuario. En Windows y macOS, Docker Desktop permite escribir en la carpeta
montada con cualquier UID. En Linux, si tu usuario no es el 1001, prepará la
carpeta una vez:

```bash
mkdir -p reportes/seguridad && chmod a+rwx reportes/seguridad
```

## Qué bloquea la integración

El job **Seguridad** de `.github/workflows/ci.yml` corre en cada PR hacia
`development` o `main`. Cada paso se ejecuta aunque otro falle, para conservar
todos los reportes, y el job falla si falla cualquiera.

| Paso | Código 0 | Código 1 | Otro código |
|---|---|---|---|
| Autoprueba de detección | Las herramientas detectan el defecto y el secreto | **Bloquea** | **Bloquea** |
| Semgrep | Sin hallazgos | **Bloquea**: hallazgo de cualquier severidad | **Bloquea**: el análisis no terminó |
| Gitleaks | Sin secretos | **Bloquea**: secreto o error de ejecución | **Bloquea** |
| OSV-Scanner | Sin vulnerabilidades | **Bloquea**: cualquier vulnerabilidad | **Bloquea**: por ejemplo, 128 si no encontró paquetes |
| OSV-Scanner de herramientas | Sin vulnerabilidades | Informativo | **Bloquea**: el análisis no terminó |

Un análisis que no pudo ejecutarse queda como incompleto, no como aprobado: un
error al descargar reglas o imágenes devuelve un código distinto de 0 y el job
falla. Ninguna herramienta usa `continue-on-error`.

## Qué hacer con un hallazgo

1. **Corregir** es lo normal: el código, la configuración o la versión afectada.
2. **Falso positivo de Semgrep:** comentario `# nosemgrep: <regla>` en la línea,
   con la justificación en el comentario anterior. Lo valida el revisor del PR.
3. **Vulnerabilidad sin corrección disponible:** excepción temporal en un
   `osv-scanner.toml` con `id`, `ignoreUntil` y `reason`. Requiere una entrada
   en el registro único con versión, evidencia, justificación, responsable,
   aprobación humana y fecha de revisión.
4. **Secreto real detectado:** revocarlo o rotarlo. Borrarlo del código o
   registrar una excepción no es suficiente.

## Demostración

`seguridad/demo_deteccion.py` crea, en una carpeta temporal ignorada por Git, un
endpoint con inyección SQL y un token ficticio de GitHub. Los analiza con los
mismos servicios y termina con código 0 solo si cada herramienta falló con el
hallazgo esperado. Después borra los archivos. El secreto se genera al ejecutar
porque, con commit, quedaría en el historial y Gitleaks fallaría siempre.

```bash
python seguridad/demo_deteccion.py
```

CI lo ejecuta como autoprueba. Los reportes quedan en `reportes/seguridad-demo/`.

## Hallazgos del primer análisis

| Herramienta | Hallazgo | Tratamiento |
|---|---|---|
| Semgrep | `backend/Dockerfile` corría como root | Corregido: usuario `app` sin privilegios |
| Semgrep | `xml.etree` en `verificar_junit.py` | Falso positivo: el XML lo genera pytest en el mismo job |
| Conftest, U2 (ítem 3.4) | Los escáneres corrían como root (EXC-01, issue #23) | Corregido: UID `1001:1001` en los cinco servicios, incluido OSV-Scanner, que U2 no detectaba por no declarar `user` |
| Semgrep | `urllib` dinámico en `resiliencia/experimento_carga.py` | Fuera del alcance: herramienta de pruebas |
| Gitleaks | Ninguno en historial ni en archivos | No aplica |
| OSV-Scanner | `vite` 5.4.21 y `esbuild` 0.21.5 | Corregido: `vite` 6.4.5 y `esbuild` 0.25.12 |
| OSV-Scanner | `source-map-js` 1.2.1 | Corregido: 1.2.2 |
| OSV-Scanner | `minimatch` 10.2.6, dependencia de `typescript-eslint` | Corregido: override a 11.0.5 |
| OSV-Scanner | `csv-parse` y `minimatch` en Artillery | Informativo: solo en el ambiente de pruebas |

## Limitaciones

- Las reglas de Semgrep se descargan del registro en cada ejecución: la imagen
  está fijada, pero las reglas pueden cambiar.
- Semgrep CE analiza cada función por separado: la regla propia no ve un
  parámetro que llega a `execute` a través de otra función o archivo.
- Gitleaks reconoce patrones y entropía: un secreto sin formato conocido puede
  pasar sin detectar.
- OSV-Scanner solo conoce vulnerabilidades publicadas y no comprueba si el
  código vulnerable se usa. Las dependencias del ETL no se analizan.
- La lista de checks obligatorios la mantiene un administrador: el job
  **Seguridad** bloquea la fusión cuando está en esa lista.
