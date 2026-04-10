FROM python:3.13-slim

# Install system dependencies for WeasyPrint
RUN apt-get update && apt-get install -y \
    python3-pip python3-cffi python3-brotli libpango-1.0-0 \
    libharfbuzz0b libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libglib2.0-0 shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Set up a new user 'user' with UID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy requirements and install
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the application
COPY --chown=user . .

# Hugging Face uses port 7860
ENV PORT=7860
EXPOSE 7860

# Start Gunicorn on port 7860
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:7860", "app:app", "--timeout", "150"]