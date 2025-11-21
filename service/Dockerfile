FROM python:3.11-slim

WORKDIR /app
COPY . /app/service
COPY src /app/src
COPY pyproject.toml /app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/service/requirements.txt \
    && pip install --no-cache-dir /app

EXPOSE 8080
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8080"]
