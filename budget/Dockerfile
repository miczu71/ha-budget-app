# Obraz przypięty (bez BUILD_FROM — Supervisor buduje lokalnie z tego pliku).
FROM python:3.12-alpine3.24

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apk add --no-cache tzdata

WORKDIR /app

# Tylko koła binarne: brak koła dla musl ma przerwać build od razu, a nie kompilować
# cryptography/pydantic-core (Rust) na urządzeniu przez kilkadziesiąt minut.
COPY requirements.txt ./
RUN pip3 install --no-cache-dir --only-binary=:all: -r requirements.txt

COPY app/pyproject.toml ./
COPY app/src ./src
RUN pip3 install --no-cache-dir --no-deps . && rm -rf src pyproject.toml build

COPY run.sh /
RUN chmod +x /run.sh

CMD ["/run.sh"]
