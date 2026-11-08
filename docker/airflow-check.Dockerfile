FROM docker:26-cli AS docker-client
FROM python:3.12-slim
COPY --from=docker-client /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-client /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
WORKDIR /source
CMD ["python", "/source/scripts/airflow-local-check.py"]
