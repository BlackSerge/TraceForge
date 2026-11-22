.PHONY: eval eval-clean sandbox-image test demo-seed

sandbox-image:
	docker build -t devpilot-sandbox:latest backend/sandbox

demo-seed:
	cd backend && PYTHONPATH=. ../.venv/bin/python scripts/demo_data.py seed

test:
	cd backend && ../.venv/bin/python -m pytest -q

eval:
	cd backend && ../.venv/bin/python scripts/run_evals.py

eval-clean:
	rm -f evals/reports/*.json
