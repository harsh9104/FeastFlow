FROM locustio/locust:2.32.4
COPY locustfile.py /home/locust/locustfile.py
# Web UI / API on 8089. Pass the target with --host (the ALB DNS name on AWS).
EXPOSE 8089
CMD ["-f", "/home/locust/locustfile.py"]
