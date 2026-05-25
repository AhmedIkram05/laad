FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./backend/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.src.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
