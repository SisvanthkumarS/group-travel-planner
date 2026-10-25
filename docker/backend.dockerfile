FROM ghcr.io/astral-sh/uv:0.13.5 AS export
WORKDIR /workspace/backend
COPY backend/ ./
RUN ["/uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--format", "requirements-txt", "--output-file", "/requirements.txt"]

# Stage 2: install dependencies using the same base as the runtime.
FROM python:3.15-slim AS dependencies
# Current Linux amd64/arm64 dependencies use prebuilt wheels; PyYAML can
# install without its optional C extension. Restore build tools only if future
# dependency changes require compiling native extensions from source.
# RUN apt-get update \
#     && apt-get install -y --no-install-recommends \
#         build-essential libffi-dev libssl-dev libpq-dev cargo rustc \
#     && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
COPY --from=export /requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt

# Stage 3: nonroot runtime, without uv or the build toolchain.
FROM python:3.15-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
# python:3.15-slim already provides CA certificates and Python's libffi runtime.
# psycopg[binary] bundles libpq; current native wheels do not need libstdc++6.
# RUN apt-get update \
#     && apt-get install -y --no-install-recommends \
#         ca-certificates libstdc++6 libffi8 libpq5 \
#     && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home \
        --shell /usr/sbin/nologin app
WORKDIR /workspace/backend
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=app:app backend/ ./
USER app:app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
