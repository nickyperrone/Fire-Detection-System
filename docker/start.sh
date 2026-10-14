#!/bin/bash
# Starts the API, the worker and the web in one container (docs/14-deploy.md). If any of them
# stops, the container stops, so Dokploy restarts it whole.
set -euo pipefail

cd /app/backend
alembic upgrade head

# On a stop from Dokploy, the three stop with the container.
trap 'kill 0' TERM INT

uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers &
python -m app.worker &
# Docker sets HOSTNAME to the container's id; the web must listen on every interface.
(cd /app/web && HOSTNAME=0.0.0.0 PORT=3000 exec node server.js) &

wait -n
exit 1
