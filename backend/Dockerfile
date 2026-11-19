# ---------- base: runtime dependencies ----------
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt requirements-llm.txt ./
RUN pip install -r requirements.txt

# Local LLM support (CPU build of PyTorch, ~700 MB). Build with --build-arg INSTALL_LLM=false to skip.
ARG INSTALL_LLM=true
RUN if [ "$INSTALL_LLM" = "true" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 && \
      pip install -r requirements-llm.txt; \
    fi

# ---------- dev: hot reload + test tools (used by docker-compose.yml) ----------
FROM base AS dev
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app", "--reload-dir", "migrations"]

# ---------- prod: no reload, non-root user ----------
FROM base AS prod
COPY . .
RUN useradd --create-home --uid 1000 ava && mkdir -p /app/logs /app/llm_models && chown -R ava /app/logs /app/llm_models
USER ava
EXPOSE 8000
# One worker: the local LLM is loaded once per process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
