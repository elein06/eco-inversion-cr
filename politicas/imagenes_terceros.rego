# Ítem 3.4, aviso U3: imágenes de terceros sin usuario explícito.
#
# U2 solo ve un "user: root" declarado. Muchas imágenes de terceros corren
# como root por defecto sin declararlo: Orlando lo encontró con OSV-Scanner
# al corregir EXC-01 (PR #24). U3 no bloquea, porque algunas imágenes
# necesitan arrancar como root y bajan de privilegios solas (PostGIS); deja a
# la vista cada servicio que alguien debe revisar.
#
# Aplica a servicios de Compose con "image" y sin "build" (no hay Dockerfile
# propio que U1 pueda revisar) que no declaran "user".
package main

import rego.v1

warn contains msg if {
	some archivo in input
	es_compose(archivo)
	some nombre, servicio in archivo.contents.services
	servicio.image
	not servicio.build
	not servicio.user
	imagen := split(servicio.image, "@")[0]
	msg := sprintf("[U3] %s: el servicio '%s' usa la imagen de terceros %s sin user explícito. Revisar con qué usuario corre y, si puede, declarar uno no root.", [archivo.path, nombre, imagen])
}
