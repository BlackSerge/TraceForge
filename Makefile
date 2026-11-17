.PHONY: eval eval-clean

eval:
	cd backend && ../.venv/bin/python scripts/run_evals.py

eval-clean:
	rm -f evals/reports/*.json
