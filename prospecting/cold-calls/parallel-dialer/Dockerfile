FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml ./
COPY parallel_dialer ./parallel_dialer
RUN pip install .

# State (recordings, progress, saved keys, the signing secret) lives in /data: mount a volume there.
RUN useradd --system --uid 10001 --home-dir /data dialer \
 && mkdir /data \
 && chown dialer /data
USER dialer
ENV DIALER_ROOT=/data \
    DIALER_HOST=0.0.0.0 \
    DIALER_PORT=8767
VOLUME /data
EXPOSE 8767

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8767/health', timeout=4)"

CMD ["python", "-m", "parallel_dialer"]
