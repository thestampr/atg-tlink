# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Bangkok

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ >/etc/timezone && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app.py ./
COPY app ./app
COPY task ./task
COPY docs ./docs
COPY sql ./sql
COPY README.md ./
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && \
    mkdir -p /app/instance

EXPOSE 5000

ENV FLASK_APP=app.py \
    FLASK_ENV=production \
    DATABASE_URL=mysql://tlink:tlinkpass@db:3306/tlink \
    PORT=5000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "app.py"]
