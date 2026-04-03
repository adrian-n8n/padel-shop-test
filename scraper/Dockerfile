FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el scraper
COPY scraper.py .

# Crear directorios de salida (se sobreescriben con volumes en docker-compose)
RUN mkdir -p /app/public/images/products /app/src/data

# Por defecto: scrape las 5 categorías, máximo 5 páginas cada una
CMD ["python", "scraper.py", "--pages", "5"]
