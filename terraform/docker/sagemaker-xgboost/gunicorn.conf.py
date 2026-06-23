"""Gunicorn configuration for SageMaker XGBoost serving container."""
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('SAGEMAKER_SERVER_PORT', '8080')}"
workers = int(os.environ.get("SAGEMAKER_SERVER_WORKERS", multiprocessing.cpu_count()))
worker_class = "sync"
timeout = 60
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
