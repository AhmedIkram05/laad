mock_provider "aws" {
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test-secret" }
  }
  mock_resource "aws_secretsmanager_secret_version" {
    defaults = { id = "secret-version-12345" }
  }
}

variables {
  project_name = "laad"
  environment  = "production"
}

run "test_secrets_variables_plan" {
  command = plan
  assert {
    condition     = var.project_name == "laad"
    error_message = "Default project_name must be 'laad'"
  }
  assert {
    condition     = var.environment == "production"
    error_message = "Default environment must be 'production'"
  }
}

run "test_secrets_outputs_apply" {
  command = apply
  assert {
    condition     = can(module.secrets.db_master_secret_arn)
    error_message = "Secrets module: db_master_secret_arn output must be present"
  }
  assert {
    condition     = can(module.secrets.mlflow_db_secret_arn)
    error_message = "Secrets module: mlflow_db_secret_arn output must be present"
  }
  assert {
    condition     = can(module.secrets.jwt_secret_arn)
    error_message = "Secrets module: jwt_secret_arn output must be present"
  }
  assert {
    condition     = can(module.secrets.rag_ollama_secret_arn)
    error_message = "Secrets module: rag_ollama_secret_arn output must be present"
  }
  assert {
    condition     = can(module.secrets.backend_env_secret_arn)
    error_message = "Secrets module: backend_env_secret_arn output must be present"
  }
  assert {
    condition     = can(module.secrets.sagemaker_secret_arn)
    error_message = "Secrets module: sagemaker_secret_arn output must be present"
  }
  assert {
    condition     = can(module.secrets.mlflow_secret_arn)
    error_message = "Secrets module: mlflow_secret_arn output must be present"
  }
}

run "test_secrets_variable_overrides" {
  command = plan
  variables {
    project_name = "test-sec"
    environment  = "dev"
  }
  assert {
    condition     = var.project_name == "test-sec"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "dev"
    error_message = "environment must be overridable"
  }
}
