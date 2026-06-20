# ---------------------------------------------------------------------------
# Secrets Manager module — LAAD platform
# ---------------------------------------------------------------------------
# Creates 7 secrets:
#   1. laad/db/master          – RDS master credentials (auto-generated password)
#   2. laad/db/mlflow          – MLflow RDS connection params
#   3. laad/app/jwt            – JWT signing key (auto-generated)
#   4. laad/rag/ollama         – RAG / Ollama API keys
#   5. laad/app/backend        – Backend runtime environment variables
#   6. laad/sagemaker          – SageMaker endpoint info (updated in Batch 3)
#   7. laad/mlflow             – MLflow tracking configuration
# ---------------------------------------------------------------------------

# ===========================================================================
# Secret 1 – RDS master credentials
# ===========================================================================

resource "random_password" "rds_master" {
  length  = 24
  special = false
}

resource "aws_secretsmanager_secret" "db_master" {
  name = "${var.project_name}/db/master"
}

resource "aws_secretsmanager_secret_version" "db_master" {
  secret_id = aws_secretsmanager_secret.db_master.id
  secret_string = jsonencode({
    username               = "atm_user"
    password               = random_password.rds_master.result
    host                   = "PLACEHOLDER"
    port                   = "5432"
    dbname                 = "atm_platform"
    db_instance_identifier = "laad-postgres"
  })
}

# ===========================================================================
# Secret 2 – MLflow RDS connection parameters
# ===========================================================================
# The password must be updated post-deploy via the AWS CLI with the actual
# rotated value once the MLflow RDS instance is provisioned.

resource "aws_secretsmanager_secret" "mlflow_db" {
  name = "${var.project_name}/db/mlflow"
}

resource "aws_secretsmanager_secret_version" "mlflow_db" {
  secret_id = aws_secretsmanager_secret.mlflow_db.id
  secret_string = jsonencode({
    host     = "laad-mlflow-postgres.cz6ckmy2u089.eu-west-2.rds.amazonaws.com"
    port     = "5432"
    dbname   = "mlflow"
    username = "mlflow_user"
    password = "PLACEHOLDER_UPDATE_VIA_CLI"
  })
}

# ===========================================================================
# Secret 3 – JWT signing key
# ===========================================================================

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "jwt" {
  name = "${var.project_name}/app/jwt"
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id = aws_secretsmanager_secret.jwt.id
  secret_string = jsonencode({
    JWT_SECRET_KEY = random_password.jwt_secret.result
  })
}

# ===========================================================================
# Secret 4 – RAG / Ollama API keys
# ===========================================================================
# API keys are placeholders and must be updated post-deploy via the AWS CLI.

resource "aws_secretsmanager_secret" "rag_ollama" {
  name = "${var.project_name}/rag/ollama"
}

resource "aws_secretsmanager_secret_version" "rag_ollama" {
  secret_id = aws_secretsmanager_secret.rag_ollama.id
  secret_string = jsonencode({
    OLLAMA_API_KEY     = "PLACEHOLDER_UPDATE_VIA_CLI"
    OPENROUTER_API_KEY = "PLACEHOLDER_UPDATE_VIA_CLI"
  })
}

# ===========================================================================
# Secret 5 – Backend runtime environment variables
# ===========================================================================

resource "aws_secretsmanager_secret" "backend_env" {
  name = "${var.project_name}/app/backend"
}

resource "aws_secretsmanager_secret_version" "backend_env" {
  secret_id = aws_secretsmanager_secret.backend_env.id
  secret_string = jsonencode({
    LAAD_ENV                 = "production"
    CORS_ORIGINS             = "PLACEHOLDER"
    VITE_API_URL             = "PLACEHOLDER"
    POSTGRES_MAX_CONNECTIONS = "20"
    LOG_LEVEL                = "INFO"
    KAFKA_BOOTSTRAP_SERVERS  = "PLACEHOLDER"
    REDIS_HOST               = "laad-redis"
    REDIS_PORT               = "6379"
    CHROMA_HOST              = "laad-chromadb"
    CHROMA_PORT              = "8000"
    REDIS_URL                = "redis://laad-redis:6379/0"
    SAGEMAKER_ENDPOINT_NAME  = "PLACEHOLDER"
    SAGEMAKER_REGION         = "eu-west-2"
    MLFLOW_TRACKING_URI      = "http://laad-mlflow-postgres.cz6ckmy2u089.eu-west-2.rds.amazonaws.com:5000"
  })
}

# ===========================================================================
# Secret 6 – SageMaker endpoint info (updated in Batch 3)
# ===========================================================================

resource "aws_secretsmanager_secret" "sagemaker" {
  name = "${var.project_name}/sagemaker"
}

resource "aws_secretsmanager_secret_version" "sagemaker" {
  secret_id = aws_secretsmanager_secret.sagemaker.id
  secret_string = jsonencode({
    SAGEMAKER_ENDPOINT_NAME = "PLACEHOLDER"
    SAGEMAKER_REGION        = "eu-west-2"
  })
}

# ===========================================================================
# Secret 7 – MLflow tracking configuration
# ===========================================================================
# No static AWS credentials — the ECS task role handles S3 access.

resource "aws_secretsmanager_secret" "mlflow" {
  name = "${var.project_name}/mlflow"
}

resource "aws_secretsmanager_secret_version" "mlflow" {
  secret_id = aws_secretsmanager_secret.mlflow.id
  secret_string = jsonencode({
    MLFLOW_TRACKING_URI     = "http://laad-mlflow-postgres.cz6ckmy2u089.eu-west-2.rds.amazonaws.com:5000"
    MLFLOW_S3_ARTIFACT_ROOT = "s3://laad-mlflow-artifacts"
    MLFLOW_REGION           = "eu-west-2"
  })
}
