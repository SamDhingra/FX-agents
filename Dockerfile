# FX-Agents app image (the IB Gateway runs in its own container)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 TZ=America/New_York
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# files copied from a Mac/zip can be owner-only (mode 600); the app runs as a non-root user, so make them readable
RUN chmod -R a+rX /app && useradd --create-home --uid 1000 fx && mkdir -p /app/data && chown -R fx:fx /app/data
USER fx

EXPOSE 8088
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/healthz', timeout=4)" || exit 1

# Mode comes from FX_MODE in .env (sim | paper | live). Live also needs I_UNDERSTAND_LIVE_TRADING=yes.
CMD ["python", "main.py"]
