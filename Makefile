.PHONY: eval eval-clean sandbox-image

sandbox-image:
	docker build -t devpilot-sandbox:latest backend/sandbox

eval:
	cd backend && ../.venv/bin/python scripts/run_evals.py

eval-clean:
	rm -f evals/reports/*.json
