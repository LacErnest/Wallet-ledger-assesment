# Image applicative. On part d'une base Python mince et on copie `uv` depuis son
# image officielle : pas besoin de l'installer via pip, et la version est figée.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /bin/uv

WORKDIR /app

# On installe d'abord les dépendances seules : tant que le lockfile ne change pas,
# cette couche reste en cache et les rebuilds applicatifs sont quasi instantanés.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
