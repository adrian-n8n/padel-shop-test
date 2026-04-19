FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7000

CMD gunicorn --bind 0.0.0.0:${PORT:-7000} --worker-class gevent --workers 1 --worker-connections 100 --timeout 300 app:app
