FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV UV_HTTP_TIMEOUT=120

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY conf ./conf
COPY prompts ./prompts
COPY docker ./docker
COPY main.py ./

RUN uv sync --frozen --no-dev
RUN chmod +x docker/agent/*.sh

EXPOSE 8000

CMD ["./docker/agent/start-agent.sh"]
