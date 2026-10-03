BACKEND = cd backend && uv run
TAG ?=

.PHONY: setup db migrate migration seed history run-once claim portfolio api worker test lint

setup:
	cd backend && uv sync
	cd frontend && npm install
	$(MAKE) db migrate

db:
	docker compose up -d --wait db

migrate:
	$(BACKEND) alembic upgrade head

migration:
	$(BACKEND) alembic revision --autogenerate -m "$(m)"

seed:
	$(BACKEND) python -m app.cli load-territories ../data/aoi/larroque_sample_fields.geojson

history:
	$(BACKEND) python -m app.cli load-history

forecast:
	$(BACKEND) python -m app.cli forecast

forecast-train:
	$(BACKEND) python -m app.forecast.train

run-once:
	$(BACKEND) python -m app.cli run-once

# The sample fields are loaded without an account; this gives them to EMAIL's account.
claim:
	$(BACKEND) python -m app.cli claim $(EMAIL)

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

.PHONY: codegen web web-check
codegen:
	$(BACKEND) python -m app.export_openapi > ../frontend/src/api/openapi.json
	cd frontend && npx openapi-typescript src/api/openapi.json -o src/api/schema.d.ts

web:
	cd frontend && npm run dev

web-check:
	cd frontend && npx tsc --noEmit && npm run lint && npx vitest run
