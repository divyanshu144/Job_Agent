.PHONY: run test fmt lint check docker-up

run:
	uvicorn backend.main:app --reload --port 8000 & cd frontend && npm run dev

test:
	pytest tests/ -v --cov=backend --cov-report=term-missing --cov-fail-under=70

fmt:
	ruff format backend/ tests/

lint:
	ruff check backend/ tests/
	mypy backend/
	python scripts/check_schema_drift.py

check:
	make fmt && make lint && make test

docker-up:
	docker-compose up --build
