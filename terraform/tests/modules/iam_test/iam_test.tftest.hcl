mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
      arn        = "arn:aws:iam::123456789012:user/test-user"
      user_id    = "AIDA1234567890EXAMPLE"
    }
  }
  mock_data "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"ecs-tasks.amazonaws.com\"},\"Action\":\"sts:AssumeRole\"}]}"
    }
  }
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/laad-github-actions-role"
    }
  }
  mock_resource "aws_iam_role_policy" {
    defaults = { id = "test-role-policy-12345" }
  }
  mock_resource "aws_iam_role_policy_attachment" {
    defaults = { id = "test-attachment-12345" }
  }
}

variables {
  project_name = "laad"
  environment  = "production"
  aws_region   = "eu-west-2"
}

run "test_iam_variables_plan" {
  command = plan
  assert {
    condition     = var.project_name == "laad"
    error_message = "Default project_name must be 'laad'"
  }
  assert {
    condition     = var.environment == "production"
    error_message = "Default environment must be 'production'"
  }
  assert {
    condition     = var.aws_region == "eu-west-2"
    error_message = "Default aws_region must be 'eu-west-2'"
  }
}

run "test_iam_outputs_apply" {
  command = apply
  assert {
    condition     = can(module.iam.github_oidc_provider_arn)
    error_message = "IAM module: github_oidc_provider_arn output must be present"
  }
  assert {
    condition     = can(module.iam.github_actions_role_arn)
    error_message = "IAM module: github_actions_role_arn output must be present"
  }
  assert {
    condition     = can(module.iam.ecs_execution_role_arn)
    error_message = "IAM module: ecs_execution_role_arn output must be present"
  }
  assert {
    condition     = can(module.iam.ecs_task_role_arn)
    error_message = "IAM module: ecs_task_role_arn output must be present"
  }
  assert {
    condition     = can(module.iam.sagemaker_execution_role_arn)
    error_message = "IAM module: sagemaker_execution_role_arn output must be present"
  }
}

run "test_iam_variable_overrides" {
  command = plan
  variables {
    project_name = "test-iam"
    environment  = "staging"
    aws_region   = "us-east-1"
  }
  assert {
    condition     = var.project_name == "test-iam"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "staging"
    error_message = "environment must be overridable"
  }
}
