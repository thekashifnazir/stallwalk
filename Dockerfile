# Hosted copy of stallwalk for Cloudflare Containers (see worker/index.js and wrangler.jsonc).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY stallwalk ./stallwalk
COPY static ./static
COPY fixtures ./fixtures
COPY voice/agent.json ./voice/agent.json
COPY vendor ./vendor
# demo caches only: derived text/JSON and 16 synthetic frames, no real footage
COPY out/pricecheck/cache.json ./out/pricecheck/cache.json
COPY out/synthetic_walk ./out/synthetic_walk
# blueprint_promo.py honours AGENTIC_COMMERCE_DIR; blueprint_reco.py hardcodes the Mac path, so mirror it with a symlink
ENV AGENTIC_COMMERCE_DIR=/app/vendor/retail-agentic-commerce
RUN mkdir -p /Users/kash/Code/sandbox/innovators-guild/blueprints \
 && ln -s /app/vendor/retail-agentic-commerce /Users/kash/Code/sandbox/innovators-guild/blueprints/Retail-Agentic-Commerce
EXPOSE 8787
CMD ["/app/.venv/bin/uvicorn", "stallwalk.app:app", "--host", "0.0.0.0", "--port", "8787"]
