# syntax=docker/dockerfile:1

FROM python:3.12.11-slim-bookworm AS build
WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1
RUN --mount=type=bind,source=requirements.txt,target=requirements.txt \
    --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile -r requirements.txt
COPY app ./app

FROM python:3.12.11-slim-bookworm AS runtime
WORKDIR /app
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup --home /tmp appuser && \
    mkdir -p /data && \
    chown 1001:1001 /data
COPY --from=build --link --chown=1001:1001 /opt/venv /opt/venv
COPY --from=build --link --chown=1001:1001 /src/app /app/app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    DATA_PATH=/data/lastro.db
USER 1001:1001
EXPOSE 8000
LABEL org.opencontainers.image.title="lastro-backend" \
      org.opencontainers.image.description="API da carteira Lastro"
ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
