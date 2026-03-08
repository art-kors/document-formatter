FROM alpine:3.20

# Устанавливаем системные зависимости для сборки пакетов с C-расширениями
RUN apk add --no-cache \
    curl \
    ca-certificates \
    libffi-dev \
    openssl-dev \
    zlib-dev \
    gcc \
    musl-dev \
    linux-headers \
    git \
    jpeg-dev \
    && update-ca-certificates

# Устанавливаем uv (musl-сборка)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Копируем файлы зависимостей
COPY .python-version ./
COPY pyproject.toml ./
COPY uv.lock ./
COPY templates ./templates

# Устанавливаем Python и зависимости
# uv автоматически скачает musl-совместимую сборку Python
RUN uv python install 3.12
RUN uv sync --frozen --no-dev  # --no-dev для продакшена

# Копируем приложение
COPY main.py ./
COPY utilities.py ./

EXPOSE 8000

# Запуск без --reload (для продакшена)
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]