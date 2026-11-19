FROM python:3.13-slim-trixie
WORKDIR /opt/helloboard
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 1000 helloboard
COPY *.py ./
COPY static/ static/
COPY templates/ templates/
USER helloboard
EXPOSE 8090
ENTRYPOINT ["python", "wifi.py"]
CMD ["--dashboard-only"]
