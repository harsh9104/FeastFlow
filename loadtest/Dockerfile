FROM python:3.12-slim
RUN pip install --no-cache-dir --retries 10 --timeout 60 locust==2.32.4
WORKDIR /app
COPY locustfile.py .
EXPOSE 8089
ENTRYPOINT ["locust", "-f", "/app/locustfile.py", "--web-host", "0.0.0.0", "--web-port", "8089"]
