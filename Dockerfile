FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir -U pip setuptools wheel \
 && pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "reposense_mcp.app:api", "--host", "0.0.0.0", "--port", "8000"]