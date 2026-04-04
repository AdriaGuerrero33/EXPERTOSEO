FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema para Pillow y lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libjpeg-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crear directorio de datos (Railway Volume se montará aquí)
RUN mkdir -p data/images credentials

# Railway usa $PORT dinámico — Streamlit debe escuchar en ese puerto
EXPOSE $PORT

CMD streamlit run dashboard.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.enableWebsocketCompression=false
