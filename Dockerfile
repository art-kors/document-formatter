FROM python:3.12-slim

# 1. Install system dependencies
# Fix: Use 'apt-get' and correct Debian package names (zlib1g-dev instead of zlib-dev)
# Removed Alpine-specific packages like 'musl-dev' and 'linux-headers'
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libffi-dev \
    libssl-dev \
    zlib1g-dev \
    gcc \
    git \
    libjpeg62-turbo-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Install uv
# Fix: Using the official image copy method is cleaner than curl | sh
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 3. Environment variables
# This makes uv sync faster and compatible with the system python
ENV UV_SYSTEM_PYTHON=1

# 4. Copy dependency definitions first (Layer Caching)
COPY pyproject.toml uv.lock ./

# 5. Install dependencies
# Fix: Removed 'uv python install' because the base image already has Python 3.12
RUN uv sync --frozen --no-dev

# 6. Copy Application Code
# Fix: Copies ALL files and folders (main.py, llm.py, pipeline/, templates/, etc.)
# This solves the issue of restructured files/folders.
COPY . .

EXPOSE 8000

# 7. Run the application
# If you moved main.py into a subfolder (e.g., src/main.py), change "main:app" to "src.main:app"
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]