FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --uid 10002 --create-home summits && mkdir -p /data && chown summits:summits /data
USER summits
ENV SUMMITS_DATA_DIR=/data
# the summit log page, with `run --ui --host 0.0.0.0`
EXPOSE 8766
ENTRYPOINT ["intervals-summits"]
# a dry run until the command says --apply
CMD ["run", "--ui", "--host", "0.0.0.0"]
