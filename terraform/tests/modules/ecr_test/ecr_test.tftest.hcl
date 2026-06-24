mock_provider "aws" {
  mock_resource "aws_ecr_repository" {
    defaults = {
      repository_url = "123456789012.dkr.ecr.eu-west-2.amazonaws.com/laad-app"
      arn            = "arn:aws:ecr:eu-west-2:123456789012:repository/laad-app"
    }
  }
  mock_resource "aws_ecr_lifecycle_policy" {
    defaults = { id = "ecr-lifecycle-12345" }
  }
}

variables {
  project_name = "laad"
  environment  = "production"
}

run "test_ecr_variables_plan" {
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

run "test_ecr_outputs_apply" {
  command = apply
  assert {
    condition     = module.ecr.repository_url == "123456789012.dkr.ecr.eu-west-2.amazonaws.com/laad-app"
    error_message = "ECR module: repository_url should match mock default"
  }
  assert {
    condition     = module.ecr.repository_arn == "arn:aws:ecr:eu-west-2:123456789012:repository/laad-app"
    error_message = "ECR module: repository_arn should match mock default"
  }
}

run "test_ecr_variable_overrides" {
  command = plan
  variables {
    project_name = "test-ecr"
    environment  = "staging"
  }
  assert {
    condition     = var.project_name == "test-ecr"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "staging"
    error_message = "environment must be overridable"
  }
}
