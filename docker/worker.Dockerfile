FROM python:3.12-slim
WORKDIR /app
COPY backend/pyproject.toml .
RUN pip install --no-cache-dir . && useradd -m worker
COPY backend/app ./app
USER worker
# Consume SQS, publica el outbox y lanza ecs:RunTask del runner (app/worker.py, semana 7)
CMD ["python", "-m", "app.worker"]
