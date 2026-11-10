# Ítem 3.4, políticas U1 y U2: los contenedores corren con un usuario no root
# declarado de forma explícita.
#
# Si el proceso corre como root dentro del contenedor, una vulnerabilidad en
# la aplicación da control total del contenedor y facilita escapar al host.
#
# Dónde se comprueba:
#   U1 - Dockerfile de las imágenes propias (backend/Dockerfile,
#        frontend/Dockerfile): la etapa final, que es la que se publica y se
#        despliega, declara USER y ese USER no es root ni el UID 0. No basta con
#        que la imagen base ya use otro usuario: tiene que estar explícito.
#   U2 - Compose: ningún servicio sobrescribe el usuario con root ("user: root"
#        o "user: 0"), porque eso anula el USER del Dockerfile.
# Las imágenes de terceros sin "user" en Compose (PostGIS, ZAP, Toxiproxy)
# conservan el usuario que define su proveedor: ver docs/politicas.md.
package main

import rego.v1

etapa_final(instrucciones) := max([i.Stage | some i in instrucciones])

usuarios_etapa_final(instrucciones) := [i.Value[0] |
	some i in instrucciones
	i.Cmd == "user"
	i.Stage == etapa_final(instrucciones)
]

deny contains msg if {
	some archivo in input
	es_dockerfile(archivo)
	count(usuarios_etapa_final(archivo.contents)) == 0
	not exceptuado("U1", archivo.path, "*")
	msg := sprintf("[U1] %s: la etapa final no declara USER. Crear un usuario sin privilegios y agregar USER <usuario> antes de CMD.", [archivo.path])
}

deny contains msg if {
	some archivo in input
	es_dockerfile(archivo)
	usuarios := usuarios_etapa_final(archivo.contents)
	count(usuarios) > 0
	ultimo := usuarios[count(usuarios) - 1]
	es_root(ultimo)
	not exceptuado("U1", archivo.path, "*")
	msg := sprintf("[U1] %s: la etapa final termina con USER %s. El último USER debe ser un usuario no root.", [archivo.path, ultimo])
}

deny contains msg if {
	some archivo in input
	es_dockerfile(archivo)
	usuarios := usuarios_etapa_final(archivo.contents)
	count(usuarios) > 0
	ultimo := usuarios[count(usuarios) - 1]
	no_verificable(ultimo)
	not exceptuado("U1", archivo.path, "*")
	msg := sprintf("[U1] %s: USER %s usa una variable y no se puede comprobar. Usar un nombre o UID fijo.", [archivo.path, ultimo])
}

deny contains msg if {
	some archivo in input
	es_compose(archivo)
	some nombre, servicio in archivo.contents.services
	es_root(servicio.user)
	not exceptuado("U2", archivo.path, nombre)
	msg := sprintf("[U2] %s: el servicio '%s' se ejecuta con user: %v. Quitar la línea o usar un usuario no root.", [archivo.path, nombre, servicio.user])
}
