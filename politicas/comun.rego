# Ítem 3.4: funciones compartidas por las políticas de contenedores.
# Conftest se ejecuta con --combine, así que input es una lista de
# {"path": ..., "contents": ...}, uno por archivo analizado.
package main

import rego.v1

es_compose(archivo) if regex.match(`(^|/)(docker-)?compose[^/]*\.ya?ml$`, archivo.path)

es_dockerfile(archivo) if regex.match(`(^|/)Dockerfile[^/]*$`, archivo.path)

es_workflow(archivo) if regex.match(`(^|/)\.github/workflows/[^/]+\.ya?ml$`, archivo.path)

# root por nombre o por UID 0, con o sin grupo ("root:root", "0:0").
es_root(usuario) if {
	nombre := split(trim_space(sprintf("%v", [usuario])), ":")[0]
	nombre in {"root", "0"}
}

# Un USER con variables no se puede comprobar de forma estática.
no_verificable(usuario) if contains(sprintf("%v", [usuario]), "$")

# Excepción vigente y registrada en politicas/datos/excepciones.yaml.
exceptuado(regla, ruta, servicio) if {
	some e in data.excepciones
	e.regla == regla
	e.archivo == ruta
	e.servicio in {servicio, "*"}
	vigente(e)
}

vigente(e) if time.parse_ns("2006-01-02", e.vence) >= time.now_ns()

# Avisos: deja a la vista cada excepción usada y las que ya vencieron.
warn contains msg if {
	some e in data.excepciones
	some archivo in input
	archivo.path == e.archivo
	vigente(e)
	msg := sprintf("[%s] excepción %s vigente hasta %s para %s (%s). Registro: %s", [e.regla, e.id, e.vence, e.archivo, e.servicio, e.registro])
}

warn contains msg if {
	some e in data.excepciones
	some archivo in input
	archivo.path == e.archivo
	not vigente(e)
	msg := sprintf("[%s] la excepción %s venció el %s: ya no se aplica", [e.regla, e.id, e.vence])
}
