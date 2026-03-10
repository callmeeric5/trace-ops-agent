FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install system dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Optimize uv settings for Docker
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Place execution environment at the front of the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Install project dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy the actual application source code
COPY . .

# Synchronize the project itself
RUN uv sync --frozen --no-dev

# Ensure db directory exists and has correct permissions
RUN mkdir -p /app/data && chmod 777 /app/data

# Default command: run the backend (using uv run)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
