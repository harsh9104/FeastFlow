FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY worker ./worker
EXPOSE 8000
# Same image runs the API (default) or the worker (command override).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
