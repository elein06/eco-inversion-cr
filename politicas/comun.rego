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
# Cada excepción nombra sus servicios uno por uno: no hay comodín, para que
# un servicio nuevo del mismo archivo no quede cubierto sin revisión (H-01).
# Las reglas de archivo completo (U1 en Dockerfile, P1 en workflows) usan "-".
exceptuado(regla, ruta, servicio) if {
	some e in data.excepciones
	e.regla == regla
	e.archivo == ruta
	servicio in e.servicios
	vigente(e)
}

# "vence" es el último día válido, hasta las 23:59:59 hora de Costa Rica
# (UTC-6, sin horario de verano). Sin la hora, "2026-12-15" se leería como
# 00:00 UTC y vencería la tarde anterior en Costa Rica (H-04).
fin_de_vigencia(e) := time.parse_rfc3339_ns(sprintf("%sT23:59:59-06:00", [e.vence]))

vigente(e) if time.now_ns() <= fin_de_vigencia(e)

# Avisos: deja a la vista cada excepción usada y las que ya vencieron.
warn contains msg if {
	some e in data.excepciones
	some archivo in input
	archivo.path == e.archivo
	vigente(e)
	msg := sprintf("[%s] excepción %s vigente hasta %s (hora de Costa Rica) para %s, servicios %s. Registro: %s", [e.regla, e.id, e.vence, e.archivo, concat(", ", e.servicios), e.registro])
}

warn contains msg if {
	some e in data.excepciones
	some archivo in input
	archivo.path == e.archivo
	not vigente(e)
	msg := sprintf("[%s] la excepción %s venció el %s: ya no se aplica", [e.regla, e.id, e.vence])
}
