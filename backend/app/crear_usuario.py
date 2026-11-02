"""
Crea (o promueve) un usuario desde la línea de comandos. Es la ÚNICA forma
de crear un administrador: /auth/registro siempre crea rol "usuario".

    cd backend
    python -m app.crear_usuario --email admin@ejemplo.cr --rol admin

La contraseña se pide por teclado (no queda en el historial de la terminal).
Para scripts de pruebas/CI se puede pasar en la variable ECO_PASSWORD.
"""

import argparse
import getpass
import os
import sys

from app.auth import hashear_password
from app.database import get_db_connection


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--nombre", default=None)
    parser.add_argument("--rol", choices=["usuario", "admin"], default="usuario")
    args = parser.parse_args()

    password = os.environ.get("ECO_PASSWORD")
    if not password:
        password = getpass.getpass("Contraseña (mín. 12 caracteres): ")
        if password != getpass.getpass("Repita la contraseña: "):
            print("Las contraseñas no coinciden.", file=sys.stderr)
            return 1
    if not 12 <= len(password) <= 128:
        print("La contraseña debe tener entre 12 y 128 caracteres.", file=sys.stderr)
        return 1

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuarios (email, nombre, password_hash, rol)
            VALUES (lower(%s), %s, %s, %s)
            ON CONFLICT (lower(email)) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    rol = EXCLUDED.rol,
                    nombre = COALESCE(EXCLUDED.nombre, usuarios.nombre),
                    intentos_fallidos = 0, bloqueado_hasta = NULL, activo = TRUE
            RETURNING usuario_id
            """,
            (args.email, args.nombre, hashear_password(password), args.rol),
        )
        usuario_id = cur.fetchone()[0]
        conn.commit()

    print(f"Usuario {usuario_id} ({args.email}) listo con rol '{args.rol}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
