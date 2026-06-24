mock_provider "aws" {
  mock_data "aws_secretsmanager_secret" {
    defaults = {
      id  = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:laad/db/master"
      arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:laad/db/master"
    }
  }
  mock_resource "aws_secretsmanager_secret_version" {
    defaults = { id = "secret-version-12345" }
  }
  mock_resource "aws_db_subnet_group" {
    defaults = {
      id   = "laad-db-subnet-group-production"
      name = "laad-db-subnet-group-production"
      arn  = "arn:aws:rds:eu-west-2:123456789012:subgrp:laad-db-subnet-group-production"
    }
  }
  mock_resource "aws_db_parameter_group" {
    defaults = {
      id   = "laad-postgres16"
      name = "laad-postgres16"
      arn  = "arn:aws:rds:eu-west-2:123456789012:pg:laad-postgres16"
    }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      id         = "laad-postgres"
      arn        = "arn:aws:rds:eu-west-2:123456789012:db:laad-postgres"
      endpoint   = "laad-postgres.123456789012.eu-west-2.rds.amazonaws.com:5432"
      port       = 5432
      db_name    = "laad_db"
      identifier = "laad-postgres"
    }
  }
}

mock_provider "random" {
  mock_resource "random_password" {
    defaults = {
      result = "mock-rds-password-24-chars!!"
    }
  }
}

variables {
  project_name       = "laad"
  environment        = "production"
  vpc_id             = "vpc-12345"
  private_subnet_ids = ["subnet-abc", "subnet-def"]
  rds_sg_id          = "sg-12345"
}

run "test_rds_variables_plan" {
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

run "test_rds_outputs_apply" {
  command = apply
  assert {
    condition     = can(module.rds.rds_endpoint)
    error_message = "RDS module: rds_endpoint output must be present"
  }
  assert {
    condition     = module.rds.rds_port == 5432
    error_message = "RDS module: rds_port should match mock default (5432)"
  }
  assert {
    condition     = module.rds.rds_db_name == "laad_db"
    error_message = "RDS module: rds_db_name should match config value"
  }
  assert {
    condition     = can(module.rds.db_master_secret_arn)
    error_message = "RDS module: db_master_secret_arn output must be present"
  }
  assert {
    condition     = can(module.rds.rds_instance_id)
    error_message = "RDS module: rds_instance_id output must be present"
  }
}

run "test_rds_variable_overrides" {
  command = plan
  variables {
    project_name       = "test-rds"
    environment        = "staging"
    vpc_id             = "vpc-99999"
    private_subnet_ids = ["subnet-xyz"]
    rds_sg_id          = "sg-99999"
  }
  assert {
    condition     = var.project_name == "test-rds"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "staging"
    error_message = "environment must be overridable"
  }
}
