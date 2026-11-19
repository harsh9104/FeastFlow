FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY worker ./worker
COPY alembic ./alembic
COPY alembic.ini entrypoint.sh ./
# Strip Windows line endings in case the script was checked out with CRLF.
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh
EXPOSE 8000
# API by default; docker-compose / user-data override the command to run the worker.
CMD ["./entrypoint.sh"]
