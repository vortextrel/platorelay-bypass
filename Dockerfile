FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y wget gnupg
COPY . .
RUN pip install fastapi uvicorn requests beautifulsoup4 playwright
RUN playwright install chromium
RUN playwright install-deps
CMD uvicorn server:app --host 0.0.0.0 --port 10000
