FROM ghcr.io/astral-sh/uv:0.13.5 AS export
WORKDIR /workspace/backend
COPY backend/ ./
RUN ["/uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--format", "requirements-txt", "--output-file", "/requirements.txt"]

FROM python:3.15-slim AS dependencies
RUN python -m venv /opt/venv
COPY --from=export /requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.15-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home \
        --shell /usr/sbin/nologin app
WORKDIR /workspace/backend
COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=app:app backend/ ./
USER app:app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
