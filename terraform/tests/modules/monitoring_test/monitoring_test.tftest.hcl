mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"budgets.amazonaws.com\"},\"Action\":\"SNS:Publish\",\"Resource\":\"arn:aws:sns:eu-west-2:123456789012:test-topic\"}]}"
    }
  }
  mock_resource "aws_sns_topic" {
    defaults = {
      id  = "test-topic"
      arn = "arn:aws:sns:eu-west-2:123456789012:test-topic"
    }
  }
  mock_resource "aws_sns_topic_policy" {
    defaults = { id = "sns-policy-12345" }
  }
  mock_resource "aws_cloudwatch_metric_alarm" {
    defaults = {
      id        = "laad-rds-cpu-credit-balance"
      arn       = "arn:aws:cloudwatch:eu-west-2:123456789012:alarm:laad-rds-cpu-credit-balance"
      alarm_name = "laad-rds-cpu-credit-balance"
    }
  }
}

variables {
  project_name = "laad"
  environment  = "production"
}

run "test_monitoring_variables_plan" {
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

run "test_monitoring_outputs_apply" {
  command = apply
  assert {
    condition     = module.monitoring.budget_sns_topic_arn == "arn:aws:sns:eu-west-2:123456789012:test-topic"
    error_message = "Monitoring module: budget_sns_topic_arn should match mock default"
  }
  assert {
    condition     = module.monitoring.rds_cpu_alarm_arn == "arn:aws:cloudwatch:eu-west-2:123456789012:alarm:laad-rds-cpu-credit-balance"
    error_message = "Monitoring module: rds_cpu_alarm_arn should match mock default"
  }
}

run "test_monitoring_variable_overrides" {
  command = plan
  variables {
    project_name = "test-mon"
    environment  = "dev"
  }
  assert {
    condition     = var.project_name == "test-mon"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "dev"
    error_message = "environment must be overridable"
  }
}
