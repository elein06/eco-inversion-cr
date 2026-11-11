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

# H-05: --privileged en las opciones de un contenedor de servicio.
test_p1_rechaza_privileged_en_opciones_de_servicio if {
	entrada := [{"path": ".github/workflows/ci.yml", "contents": {"jobs": {"a": {"services": {"db": {"image": "postgres", "options": "--health-cmd pg_isready --privileged"}}}}}}]
	some msg in deny with input as entrada with data.excepciones as sin_excepciones
	contains(msg, "services.db.options")
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

# H-02: un user con variables puede terminar en root.
test_u2_rechaza_user_con_variable if {
	every usuario in ["${USUARIO:-root}", "${UID}:${GID}", "$USUARIO"] {
		count(deny) == 1 with input as compose({"api": {"user": usuario}})
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
	"servicios": ["api"], "vence": vence, "registro": "#0",
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

# H-01: la excepción solo cubre los servicios que nombra, y "*" no es comodín.
test_excepcion_no_cubre_servicio_nuevo_del_mismo_archivo if {
	excepciones := [{
		"id": "EXC-X", "regla": "U2", "archivo": "docker-compose.yml",
		"servicios": ["semgrep", "gitleaks"], "vence": "2099-01-01", "registro": "#0",
	}]
	resultado := deny with input as compose({
		"semgrep": {"user": "root"}, "gitleaks": {"user": "root"}, "prueba-h01": {"user": "root"},
	})
		with data.excepciones as excepciones
	count(resultado) == 1
	some msg in resultado
	contains(msg, "prueba-h01")
}

test_asterisco_no_es_comodin if {
	excepciones := [{
		"id": "EXC-X", "regla": "U2", "archivo": "docker-compose.yml",
		"servicios": ["*"], "vence": "2099-01-01", "registro": "#0",
	}]
	count(deny) == 1 with input as compose({"api": {"user": "root"}})
		with data.excepciones as excepciones
}

# H-04: "vence" incluye todo ese día en hora de Costa Rica (UTC-6).
test_excepcion_vigente_el_ultimo_dia_en_costa_rica if {
	# 2026-12-15 20:00 en Costa Rica = 2026-12-16 02:00 UTC
	ahora := time.parse_rfc3339_ns("2026-12-15T20:00:00-06:00")
	count(deny) == 0 with input as compose({"api": {"user": "root"}})
		with data.excepciones as excepcion("2026-12-15")
		with time.now_ns as ahora
}

test_excepcion_vencida_al_dia_siguiente_en_costa_rica if {
	ahora := time.parse_rfc3339_ns("2026-12-16T00:00:01-06:00")
	count(deny) == 1 with input as compose({"api": {"user": "root"}})
		with data.excepciones as excepcion("2026-12-15")
		with time.now_ns as ahora
}

# --- U3 (aviso): imágenes de terceros sin user ---

avisos_u3(entrada) := [msg | some msg in warn with input as entrada with data.excepciones as sin_excepciones; startswith(msg, "[U3]")]

test_u3_avisa_imagen_de_terceros_sin_user if {
	avisos := avisos_u3(compose({"osv": {"image": "ghcr.io/google/osv-scanner:v2.7.0@sha256:abc"}}))
	count(avisos) == 1
	contains(avisos[0], "'osv'")
	not contains(avisos[0], "sha256")
}

test_u3_no_avisa_con_user_o_imagen_propia if {
	entrada := compose({
		"escaner": {"image": "semgrep/semgrep", "user": "1001:1001"},
		"api": {"build": ".", "image": "eco/api"},
	})
	count(avisos_u3(entrada)) == 0
}

test_u3_no_bloquea if {
	count(deny) == 0 with input as compose({"db": {"image": "postgis/postgis:16-3.4"}})
		with data.excepciones as sin_excepciones
}
