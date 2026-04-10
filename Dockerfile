FROM python:3.13-slim

# Install system dependencies for WeasyPrint and PDF generation
RUN apt-get update && apt-get install -y \
    python3-pip python3-cffi python3-brotli libpango-1.0-0 \
    libharfbuzz0b libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libglib2.0-0 shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set dynamic port for Render
ENV PORT=10000
EXPOSE 10000

# Start with Gunicorn
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "app:app", "--timeout", "150"]