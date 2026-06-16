FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[prod]"

COPY . .

EXPOSE 8000

# gunicorn for Linux prod; threads since work is I/O-bound (parallel source fan-out).
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "8", "wsgi:app"]
