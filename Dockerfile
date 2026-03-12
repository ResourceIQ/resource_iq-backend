FROM python:3.12.2

ENV PYTHONUNBUFFERED=1

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app/

ENV PATH="/app/.venv/bin:$PATH"

COPY ./pyproject.toml ./uv.lock /app/

RUN uv sync --frozen --no-install-project --package app

COPY ./scripts /app/scripts

COPY ./alembic.ini /app/
COPY ./app /app/app

RUN uv sync --frozen --package app

WORKDIR /app/

CMD ["sh", "-c", "fastapi run --workers 4 --host 0.0.0.0 --port ${PORT:-8080} app/main.py"]
