# Stage 1: build SPA (no-op until frontend/package.json exists)
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/ ./
RUN if [ -f package.json ]; then npm ci && npm run build; else mkdir -p dist; fi

# Stage 2: runtime
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/srv
WORKDIR /srv
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist ./app/static
RUN chmod +x entrypoint.sh
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION
EXPOSE 8000
CMD ["./entrypoint.sh"]
