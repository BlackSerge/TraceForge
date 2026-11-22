.PHONY: eval eval-clean sandbox-image test

sandbox-image:
	docker build -t devpilot-sandbox:latest backend/sandbox

test:
	cd backend && ../.venv/bin/python -m pytest -q

eval:
	cd backend && ../.venv/bin/python scripts/run_evals.py

eval-clean:
	rm -f evals/reports/*.json
