FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Runtime deps (cached layer) + a WSGI server for self-hosting.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 8000

# Threads since work is I/O-bound (parallel source fan-out). The app package is
# importable from WORKDIR, so no install step is needed.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "8", "wsgi:app"]
