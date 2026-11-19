# ---- 1. build the React app ----
FROM node:20-alpine AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. API + worker image (same image, different command) ----
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/worker ./worker
COPY backend/alembic ./alembic
COPY backend/alembic.ini backend/entrypoint.sh ./
# Strip Windows line endings in case the script was checked out with CRLF.
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh
COPY --from=frontend /web/dist ./static
EXPOSE 8000
# API by default; docker-compose / EC2 user-data override the command to run the worker.
CMD ["./entrypoint.sh"]
