FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Create temp dirs (Render/Docker use /tmp)
RUN mkdir -p /tmp/bot_session /tmp/downloads /tmp/outputs

# Expose port for health checks
EXPOSE 8080

# Start bot (built-in health server handles PORT)
CMD ["python", "main.py"]
