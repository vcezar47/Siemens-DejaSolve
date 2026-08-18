# Déjà Solve — one image, two jobs: serve the API + UI, or re-run every number.
#
# The pitch is a platform, so the thing that ships is the service. `app.py`
# resolves its paths against its own file rather than the working directory,
# so it starts correctly from anywhere in the container.
#
#   docker compose up                          # the demo, on :8000
#   docker compose --profile reproduce up       # regenerate all the numbers
#
# Deliberately a single stage: there is nothing to compile, the dependency set
# is three wheels, and a multi-stage build here would be complexity for its own
# sake on a slide that is about architecture, not about Docker.

FROM python:3.13-slim

# - PYTHONDONTWRITEBYTECODE: no __pycache__ owned by root in a mounted repo
# - PYTHONUNBUFFERED: run_all.py prints its progress; buffering hides it
# - MPLCONFIGDIR: matplotlib wants a writable config dir, and the app user's
#   home is not it by default — without this every figure logs a warning
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

# Dependencies first, so editing source does not invalidate the wheel cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user: this is the container that would face a network.
# On Linux, `docker compose --profile reproduce` writes into the mounted repo
# as this UID — override with `user: "${UID}:${GID}"` if the ownership matters.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

# /api/health reports archive size and which ingest backends are reachable.
# The Ollama probe inside it has a 3s timeout and fails closed when no model
# server is present, hence the unusually generous --timeout.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=8).status == 200 else 1)"

# 0.0.0.0 rather than the app's 127.0.0.1 default: inside a container the
# loopback default would refuse every connection from the published port.
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8000"]
