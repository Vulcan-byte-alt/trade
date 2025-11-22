FROM python:3.11-slim

WORKDIR /app

# Copy base bot template (universal infrastructure)
COPY ../base-bot-template/ /app/base/

# Copy strategy-specific files
COPY . /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/base/requirements.txt
RUN if [ -f /app/requirements.txt ]; then pip install --no-cache-dir -r /app/requirements.txt; fi

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV STRATEGY_TYPE=quantum_momentum_pro

# Run the strategy bot
CMD ["python", "/app/startup.py"]
