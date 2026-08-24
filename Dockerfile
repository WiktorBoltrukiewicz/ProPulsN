# ProPulsN — one container, one port, one process.
#
# Serves the WebSocket API, the static frontend and GET /files/ on :8000, and
# spawns `python main.py <config>` as a subprocess for each solve, exactly as
# the app does outside a container.
#
#   docker build -t propulsn .
#   docker run --rm -p 8000:8000 \
#     -v "$PWD/params:/app/params" -v "$PWD/results:/app/results" propulsn
#
# Or just `docker compose up`, which sets those mounts for you.
#
# This image targets SELF-HOSTING. It has no authentication and no request
# limits, because the app has none — see "Public hosting" in CLAUDE.md before
# putting it anywhere the open internet can reach.

FROM python:3.12-slim

# PYTHONUNBUFFERED is load-bearing, not hygiene: the solver's stdout is
# streamed to the browser line by line, and a buffered pipe stalls the live
# convergence chart until the run ends.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so editing the source does not re-resolve numpy/scipy.
# backend/requirements.txt deliberately excludes matplotlib — the web app
# draws its own charts, and it is the single largest thing we can leave out.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# The layout has to be preserved: core/__init__.py walks four directories up
# from itself to find REPO_ROOT, so backend/, frontend/, params/ and results/
# must sit side by side under /app.
COPY backend/ backend/
COPY frontend/ frontend/
COPY params/ params/
COPY main.py README.md LICENSE NOTICE ./

# Run as a normal user. The two writable directories are chowned so a fresh
# container works with no mounts at all; a bind-mounted host directory brings
# its own ownership, so on Linux see the README if writes are refused.
RUN useradd --create-home --uid 1000 propulsn \
    && mkdir -p results \
    && chown -R propulsn:propulsn /app/params /app/results
USER propulsn

EXPOSE 8000

# --host 0.0.0.0 so the port is reachable from outside the container. There is
# no --reload here: it watches the filesystem and doubles the process count for
# no benefit in an image.
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4).status == 200 else 1)"
