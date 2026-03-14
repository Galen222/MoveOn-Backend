# tests/conftest.py
#
# Variables de entorno para el entorno de test.
# Los secretos JWT deben tener al menos 32 bytes para HS256 (RFC 7518 §3.2).
# Secretos más cortos hacen pasar los tests pero generan InsecureKeyLengthWarning.

import os

DEFAULT_ENV = {
    "DB_USER": "test",
    "DB_PASSWORD": "test",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "test",
    "APP_ID": "test-app",
    # ≥ 32 caracteres para silenciar InsecureKeyLengthWarning de PyJWT
    "APP_SESSION_SECRET": "test-app-session-secret-padding-ok",
    "ACCESS_TOKEN_SECRET": "test-access-secret-padding-xxxxx-ok",
    "REFRESH_TOKEN_SECRET": "test-refresh-secret-padding-xxxx-ok",
    "REFRESH_HASH_SECRET": "test-refresh-hash-secret-padding-ok",
    "CODE_HASH_SECRET": "test-code-hash-secret-padding-xxxx",
    "EMAIL_HOST": "smtp.example.com",
    "EMAIL_USER": "test@example.com",
    "EMAIL_PASS": "test-pass",
    "STORAGE_TYPE": "local",
    "ENABLE_DOCS": "false",
    "ENABLE_CORS": "false",
}

for key, value in DEFAULT_ENV.items():
    os.environ.setdefault(key, value)
