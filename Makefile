.PHONY: install run test test-unit test-ui eval docker-up docker-down docker-test seed

install:
	pip install -r requirements.txt -r requirements-dev.txt
	playwright install chromium

run:
	uvicorn app.main:app --reload --port 8000

test: test-unit test-ui

test-unit:
	MESH_MOCK=1 pytest tests/unit tests/integration -q

test-ui:
	MESH_MOCK=1 pytest tests/ui -q --browser chromium

eval:
	python scripts/evaluate.py --briefs 4 --platforms linkedin,x

seed:
	curl -s -X POST http://localhost:8000/api/demo/seed | python -m json.tool | head -30

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-test:
	docker compose -f docker-compose.test.yml run --rm tests
