FROM python:3.13-slim-trixie
WORKDIR /opt/helloboard
COPY requirements.txt ./
ENV PIP_NO_CACHE_DIR=1
COPY install.sh start.sh ./
RUN bash install.sh --local && useradd -m -u 1000 helloboard
COPY *.py ./
COPY static/ static/
COPY templates/ templates/
USER helloboard
EXPOSE 8090
ENTRYPOINT ["bash", "/opt/helloboard/start.sh"]
