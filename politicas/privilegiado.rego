# Ítem 3.4, política P1: ningún contenedor se ejecuta en modo privilegiado.
#
# Un contenedor privilegiado tiene todas las capacidades del kernel y acceso a
# los dispositivos del host: escapar de él equivale a tener root en el host.
#
# Dónde se comprueba:
#   - Compose (docker-compose*.yml, dast/docker-compose.yml): "privileged: true".
#   - Workflows de GitHub Actions: "--privileged" en comandos o en las opciones
#     de contenedores de servicio.
# Un Dockerfile no puede pedir modo privilegiado; eso se decide al ejecutar.
package main

import rego.v1

deny contains msg if {
	some archivo in input
	es_compose(archivo)
	some nombre, servicio in archivo.contents.services
	lower(sprintf("%v", [servicio.privileged])) == "true"
	not exceptuado("P1", archivo.path, nombre)
	msg := sprintf("[P1] %s: el servicio '%s' usa privileged: true. Quitarlo y, si necesita una capacidad concreta, pedirla con cap_add.", [archivo.path, nombre])
}

deny contains msg if {
	some archivo in input
	es_workflow(archivo)
	walk(archivo.contents, [ruta, valor])
	is_string(valor)
	contains(valor, "--privileged")
	not exceptuado("P1", archivo.path, "*")
	msg := sprintf("[P1] %s: '--privileged' en %s. Los workflows no ejecutan contenedores privilegiados.", [archivo.path, concat(".", [sprintf("%v", [p]) | some p in ruta])])
}
