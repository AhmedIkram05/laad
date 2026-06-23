# SageMaker XGBoost Serving Container
# Based on official Python 3.10 slim image
FROM python:3.10-slim

LABEL com.amazonaws.sagemaker.capabilities.accept-bind-to-port="8080"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    xgboost==3.2.0 \
    flask==3.1.1 \
    gunicorn==23.0.0 \
    pandas==2.2.3 \
    numpy==1.26.4

# Create model directory
RUN mkdir -p /opt/ml/model

# Copy serving code
COPY serve.py /usr/local/bin/serve.py
COPY gunicorn.conf.py /etc/gunicorn.conf.py
RUN chmod +x /usr/local/bin/serve.py

# Environment
ENV SAGEMAKER_SERVER_PORT=8080
ENV SAGEMAKER_MODEL_PATH=/opt/ml/model/xgboost-model
ENV PYTHONPATH=/usr/local/bin

EXPOSE 8080

# Use gunicorn to serve the Flask app
ENTRYPOINT ["gunicorn", "--config", "/etc/gunicorn.conf.py", "serve:app"]
