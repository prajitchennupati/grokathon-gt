PY      := $(CURDIR)/.venv/bin/python
BACKEND := cd backend &&
FRONT   := cd frontend &&

.PHONY: setup dev demo test backend frontend scenario precache build

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements.txt
	$(FRONT) npm install

# Backend (autoreload) + frontend dev server. Ctrl-C stops both.
dev:
	@trap 'kill 0' INT TERM; \
	($(BACKEND) $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app) & \
	($(FRONT) npx vite --host 127.0.0.1 --port 5173) & \
	wait

# Demo: demo scenario, fallback mode for every Bot, demo-script sidebar. OFFLINE=1 forces the LLM cache.
demo:
	@trap 'kill 0' INT TERM; \
	(cd backend && DEMO_MODE=1 CLEARANCE_OFFLINE=$(or $(OFFLINE),0) $(PY) -m app.serve --demo $(if $(filter 1,$(OFFLINE)),--offline,)) & \
	($(FRONT) npx vite --host 127.0.0.1 --port 5173) & \
	wait

test:
	$(BACKEND) $(PY) -m pytest -q
	$(FRONT) npx tsc --noEmit -p .

scenario:
	$(BACKEND) $(PY) -m scenarios.build_demo

build:
	$(FRONT) npm run build
