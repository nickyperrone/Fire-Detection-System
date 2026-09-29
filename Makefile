BACKEND = cd backend && uv run
TAG ?=

.PHONY: setup db migrate migration seed run-once portfolio api worker test lint

setup:
	cd backend && uv sync
	$(MAKE) db migrate

db:
	docker compose up -d --wait db

migrate:
	$(BACKEND) alembic upgrade head

migration:
	$(BACKEND) alembic revision --autogenerate -m "$(m)"

seed:
	$(BACKEND) python -m app.cli load-territories ../data/aoi/larroque_sample_fields.geojson

run-once:
	$(BACKEND) python -m app.cli run-once

portfolio:
	$(BACKEND) python -m app.cli portfolio $(if $(TAG),--tag "$(TAG)")

api:
	$(BACKEND) uvicorn app.main:app --reload

worker:
	$(BACKEND) python -m app.worker

test:
	$(BACKEND) pytest

lint:
	$(BACKEND) ruff check . && $(BACKEND) ruff format --check .
