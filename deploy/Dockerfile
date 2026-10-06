FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY apps ./apps
USER 10001
EXPOSE 8080
# SIGTERM reaches uvicorn directly (exec form), which drains requests for HTTP_GRACEFUL_SHUTDOWN_S.
CMD ["python", "-m", "apps.api"]
