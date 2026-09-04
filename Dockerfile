FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md VERSION ./
COPY src ./src
COPY apps ./apps
COPY configs ./configs
COPY scripts ./scripts

RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
