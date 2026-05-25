# Custom MLflow image with PostgreSQL and AWS S3 dependencies
FROM ghcr.io/mlflow/mlflow:v3.1.1

# Install PostgreSQL driver (psycopg2-binary) and AWS SDK (boto3)
# These are required for:
# - PostgreSQL as backend store (RDS)
# - S3 as artifact store
RUN pip install --no-cache-dir psycopg2-binary==2.9.9 boto3==1.34.0

# Verify installation
RUN python -c "import psycopg2; import boto3; print('psycopg2 and boto3 installed successfully')"
