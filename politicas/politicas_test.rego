# Pruebas de las políticas del ítem 3.4: conftest verify --policy politicas
package main

import rego.v1

dockerfile(instrucciones) := [{"path": "backend/Dockerfile", "contents": instrucciones}]

compose(servicios) := [{"path": "docker-compose.yml", "contents": {"services": servicios}}]

instr(cmd, valor, etapa) := {"Cmd": cmd, "Value": [valor], "Stage": etapa}

sin_excepciones := []

# --- U1: USER en la etapa final del Dockerfile ---

test_u1_permite_usuario_no_root if {
	entrada := dockerfile([instr("from", "python:3.12-slim", 0), instr("user", "app", 0)])
	count(deny) == 0 with input as entrada with data.excepciones as sin_excepciones
}

test_u1_rechaza_sin_user if {
	entrada := dockerfile([instr("from", "python:3.12-slim", 0), instr("cmd", "python", 0)])
	some msg in deny with input as entrada with data.excepciones as sin_excepciones
	startswith(msg, "[U1]")
}

test_u1_rechaza_root_por_nombre_y_uid if {
	every usuario in ["root", "0", "root:root", "0:0"] {
		entrada := dockerfile([instr("from", "python:3.12-slim", 0), instr("user", usuario, 0)])
		count(deny) == 1 with input as entrada with data.excepciones as sin_excepciones
	}
}

test_u1_cuenta_solo_el_ultimo_user if {
	entrada := dockerfile([instr("from", "x", 0), instr("user", "app", 0), instr("user", "root", 0)])
	count(deny) == 1 with input as entrada with data.excepciones as sin_excepciones
}

# El USER de una etapa de compilación no cuenta: la imagen final es otra.
test_u1_user_solo_en_etapa_de_compilacion if {
	entrada := dockerfile([
		instr("from", "node:24-alpine", 0), instr("user", "node", 0),
		instr("from", "nginx", 1), instr("copy", "dist", 1),
	])
	count(deny) == 1 with input as entrada with data.excepciones as sin_excepciones
}

test_u1_multietapa_con_user_final if {
	entrada := dockerfile([
		instr("from", "node:24-alpine", 0),
		instr("from", "nginx", 1), instr("user", "101", 1),
	])
	count(deny) == 0 with input as entrada with data.excepciones as sin_excepciones
}

test_u1_rechaza_user_con_variable if {
	entrada := dockerfile([instr("from", "x", 0), instr("user", "$USUARIO", 0)])
	count(deny) == 1 with input as entrada with data.excepciones as sin_excepciones
}

# --- P1: modo privilegiado ---

test_p1_rechaza_privileged if {
	some msg in deny with input as compose({"api": {"build": ".", "privileged": true}})
		with data.excepciones as sin_excepciones
	startswith(msg, "[P1]")
}

test_p1_permite_privileged_false if {
	count(deny) == 0 with input as compose({"api": {"build": ".", "privileged": false}})
		with data.excepciones as sin_excepciones
}

test_p1_rechaza_privileged_en_workflow if {
	entrada := [{"path": ".github/workflows/ci.yml", "contents": {"jobs": {"a": {"steps": [{"run": "docker run --privileged alpine"}]}}}}]
	count(deny) == 1 with input as entrada with data.excepciones as sin_excepciones
}

# --- U2: user root en Compose ---

test_u2_rechaza_user_root if {
	every usuario in ["root", "0", "0:0", 0] {
		count(deny) == 1 with input as compose({"api": {"build": ".", "user": usuario}})
			with data.excepciones as sin_excepciones
	}
}

test_u2_permite_user_no_root_y_sin_user if {
	count(deny) == 0 with input as compose({"api": {"user": "1000:1000"}, "db": {"image": "postgis/postgis"}})
		with data.excepciones as sin_excepciones
}

# --- Excepciones ---

excepcion(vence) := [{
	"id": "EXC-X", "regla": "U2", "archivo": "docker-compose.yml",
	"servicio": "api", "vence": vence, "registro": "#0",
}]

test_excepcion_vigente_permite if {
	count(deny) == 0 with input as compose({"api": {"user": "root"}})
		with data.excepciones as excepcion("2099-01-01")
}

test_excepcion_vencida_no_permite if {
	count(deny) == 1 with input as compose({"api": {"user": "root"}})
		with data.excepciones as excepcion("2000-01-01")
}

test_excepcion_no_cubre_otro_servicio if {
	count(deny) == 1 with input as compose({"worker": {"user": "root"}})
		with data.excepciones as excepcion("2099-01-01")
}

test_excepcion_no_cubre_otra_regla if {
	count(deny) == 1 with input as compose({"api": {"privileged": true}})
		with data.excepciones as excepcion("2099-01-01")
}
