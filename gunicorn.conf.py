import os


# Railpack detecta Django y genera el comando de Gunicorn automáticamente.
# Mantener la concurrencia en este archivo evita depender de flags del
# startCommand, que Railpack puede simplificar durante el build.
workers = int(os.getenv("WEB_CONCURRENCY", "3"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "2"))

# Ajustes conservadores para una app web tradicional detrás del proxy de Railway.
timeout = 30
graceful_timeout = 30
keepalive = 5
