FROM python:3.12-slim AS base

WORKDIR /app

# System deps for weasyprint (optional, reports extra)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
        libffi-dev libcairo2 && \
    rm -rf /var/lib/apt/lists/*

# Install package with server + analysis extras
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[server,analysis,reports]"

# Default workspace
ENV PA_WORKSPACE_DIR=/data/persona_workspace
VOLUME /data

EXPOSE 8000

CMD ["uvicorn", "persona_agent.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
