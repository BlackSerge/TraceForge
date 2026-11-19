# Image used by tools.run_tests. pytest is baked in because the container runs with --network=none.
FROM python:3.15-slim
RUN pip install --no-cache-dir pytest==9.2.0
WORKDIR /repo
