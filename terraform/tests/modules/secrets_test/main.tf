terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
    random = { source = "hashicorp/random" }
  }
}

variable "project_name" { type = string }
variable "environment"  { type = string }

module "secrets" {
  source = "../../../modules/secrets"

  project_name = var.project_name
  environment  = var.environment
}

output "db_master_secret_arn"    { value = module.secrets.db_master_secret_arn }
output "mlflow_db_secret_arn"    { value = module.secrets.mlflow_db_secret_arn }
output "jwt_secret_arn"          { value = module.secrets.jwt_secret_arn }
output "rag_ollama_secret_arn"   { value = module.secrets.rag_ollama_secret_arn }
output "backend_env_secret_arn"  { value = module.secrets.backend_env_secret_arn }
output "sagemaker_secret_arn"    { value = module.secrets.sagemaker_secret_arn }
output "mlflow_secret_arn"       { value = module.secrets.mlflow_secret_arn }
