# Gate merge của MỌI session: make smoke phải xanh trước khi push (<60s, không Docker/model)
.PHONY: smoke test up

smoke:
	uv run python -c "import api.main, api.schemas"
	uv run pytest -q -m "not heavy"

test:
	uv run pytest -q -m "not llm_live"

up:
	docker compose up -d --build
