# ---------------------------------------------------------------------------
# Outputs — Secrets Manager module
# ---------------------------------------------------------------------------

# Secret 1 – RDS master
output "db_master_secret_arn" {
  description = "ARN of the RDS master secret (laad/db/master)"
  value       = aws_secretsmanager_secret.db_master.arn
}

output "db_master_password" {
  description = "Auto-generated RDS master password"
  value       = random_password.rds_master.result
  sensitive   = true
}

# Secret 2 – MLflow DB
output "mlflow_db_secret_arn" {
  description = "ARN of the MLflow DB connection secret (laad/db/mlflow)"
  value       = aws_secretsmanager_secret.mlflow_db.arn
}

# Secret 3 – JWT
output "jwt_secret_arn" {
  description = "ARN of the JWT secret (laad/app/jwt)"
  value       = aws_secretsmanager_secret.jwt.arn
}

output "jwt_secret_key" {
  description = "Auto-generated JWT signing key"
  value       = random_password.jwt_secret.result
  sensitive   = true
}

# Secret 4 – RAG / Ollama
output "rag_ollama_secret_arn" {
  description = "ARN of the RAG/Ollama secret (laad/rag/ollama)"
  value       = aws_secretsmanager_secret.rag_ollama.arn
}

# Secret 5 – Backend env
output "backend_env_secret_arn" {
  description = "ARN of the backend env secret (laad/app/backend)"
  value       = aws_secretsmanager_secret.backend_env.arn
}

# Secret 6 – SageMaker
output "sagemaker_secret_arn" {
  description = "ARN of the SageMaker secret (laad/sagemaker)"
  value       = aws_secretsmanager_secret.sagemaker.arn
}

# Secret 7 – MLflow tracking
output "mlflow_secret_arn" {
  description = "ARN of the MLflow tracking secret (laad/mlflow)"
  value       = aws_secretsmanager_secret.mlflow.arn
}
