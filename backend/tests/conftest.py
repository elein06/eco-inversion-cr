"""
Configuración común de pruebas.

Las variables se fijan ANTES de importar `app`, porque app.config lee el
entorno al importarse. Las variables de entorno ganan sobre el .env real del
repositorio, así que las pruebas nunca usan la base ni el secreto de nadie.
"""

import os

os.environ["JWT_SECRET"] = "secreto-solo-para-pruebas-" + "x" * 32
os.environ.setdefault("LOGIN_MAX_INTENTOS", "5")
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
