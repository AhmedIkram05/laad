mock_provider "aws" {
  mock_resource "aws_ecs_cluster" {
    defaults = {
      id   = "arn:aws:ecs:eu-west-2:123456789012:cluster/laad-cluster"
      arn  = "arn:aws:ecs:eu-west-2:123456789012:cluster/laad-cluster"
      name = "laad-cluster"
    }
  }
  mock_resource "aws_ecs_cluster_capacity_providers" {
    defaults = { id = "laad-cluster" }
  }
  mock_resource "aws_service_discovery_private_dns_namespace" {
    defaults = {
      id  = "ns-1234567890abcdef0"
      arn = "arn:aws:servicediscovery:eu-west-2:123456789012:namespace/ns-1234567890abcdef0"
    }
  }
  mock_resource "aws_service_discovery_service" {
    defaults = {
      id  = "srv-1234567890abcdef0"
      arn = "arn:aws:servicediscovery:eu-west-2:123456789012:service/srv-1234567890abcdef0"
      name = "redis"
    }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      id  = "/ecs/laad-api"
      arn = "arn:aws:logs:eu-west-2:123456789012:log-group:/ecs/laad-api:*"
    }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = {
      id         = "laad-api"
      arn        = "arn:aws:ecs:eu-west-2:123456789012:task-definition/laad-api:1"
      family     = "laad-api"
      revision   = 1
    }
  }
  mock_resource "aws_lb" {
    defaults = {
      id          = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:loadbalancer/app/laad-alb/1234567890abcdef"
      arn         = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:loadbalancer/app/laad-alb/1234567890abcdef"
      arn_suffix  = "app/laad-alb/1234567890abcdef"
      dns_name    = "laad-alb-1234567890.eu-west-2.elb.amazonaws.com"
      zone_id     = "Z3KABCDEFGHIJK"
      name        = "laad-alb"
    }
  }
  mock_resource "aws_lb_target_group" {
    defaults = {
      id   = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:targetgroup/laad-api-tg/1234567890abcdef"
      arn  = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:targetgroup/laad-api-tg/1234567890abcdef"
      name = "laad-api-tg"
    }
  }
  mock_resource "aws_lb_listener" {
    defaults = {
      id  = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:listener/app/laad-alb/1234567890abcdef/1234567890abcdef"
      arn = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:listener/app/laad-alb/1234567890abcdef/1234567890abcdef"
    }
  }
  mock_resource "aws_ecs_service" {
    defaults = {
      id   = "arn:aws:ecs:eu-west-2:123456789012:service/laad-cluster/laad-api"
      name = "laad-api"
    }
  }
  mock_resource "aws_cloudwatch_log_metric_filter" {
    defaults = { id = "APIErrorCount" }
  }
  mock_resource "aws_cloudwatch_dashboard" {
    defaults = {
      id = "laad-dashboard-production"
      dashboard_name = "laad-dashboard-production"
    }
  }
}

variables {
  project_name               = "laad"
  environment                = "production"
  vpc_id                     = "vpc-12345"
  public_subnet_ids          = ["subnet-pub1", "subnet-pub2"]
  private_subnet_ids         = ["subnet-priv1", "subnet-priv2"]
  alb_sg_id                  = "sg-alb-12345"
  ecs_api_sg_id              = "sg-api-12345"
  ecs_consumer_sg_id         = "sg-consumer-12345"
  ecs_generator_sg_id        = "sg-generator-12345"
  redis_sg_id                = "sg-redis-12345"
  chromadb_sg_id             = "sg-chromadb-12345"
  ecs_execution_role_arn     = "arn:aws:iam::123456789012:role/laad-ecs-execution-role"
  ecs_task_role_arn          = "arn:aws:iam::123456789012:role/laad-ecs-task-role"
  ecr_repository_url         = "123456789012.dkr.ecr.eu-west-2.amazonaws.com/laad-app"
  kafka_bootstrap_servers    = "10.0.1.100:9092"
  rds_endpoint               = "laad-postgres.123456789012.eu-west-2.rds.amazonaws.com:5432"
  rds_port                   = "5432"
  rds_db_name                = "laad_db"
  db_master_secret_arn       = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:laad/db/master"
  jwt_secret_arn             = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:laad/jwt"
  sagemaker_secret_arn       = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:laad/sagemaker"
  mlflow_tracking_secret_arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:laad/mlflow"
  rag_ollama_secret_arn      = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:laad/rag-ollama"
  aws_region                 = "eu-west-2"
  cors_origins               = "https://example.com"
}

run "test_ecs_variables_plan" {
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

run "test_ecs_outputs_apply" {
  command = apply
  assert {
    condition     = can(module.ecs.ecs_cluster_name)
    error_message = "ECS module: ecs_cluster_name output must be present"
  }
  assert {
    condition     = can(module.ecs.ecs_cluster_id)
    error_message = "ECS module: ecs_cluster_id output must be present"
  }
  assert {
    condition     = can(module.ecs.alb_arn)
    error_message = "ECS module: alb_arn output must be present"
  }
  assert {
    condition     = can(module.ecs.alb_dns_name)
    error_message = "ECS module: alb_dns_name output must be present"
  }
  assert {
    condition     = can(module.ecs.alb_zone_id)
    error_message = "ECS module: alb_zone_id output must be present"
  }
  assert {
    condition     = can(module.ecs.target_group_arn)
    error_message = "ECS module: target_group_arn output must be present"
  }
}

run "test_ecs_variable_overrides" {
  command = plan
  variables {
    project_name               = "test-ecs"
    environment                = "staging"
    aws_region                 = "us-east-1"
    vpc_id                     = "vpc-99999"
    public_subnet_ids          = ["subnet-x", "subnet-y"]
    private_subnet_ids         = ["subnet-z"]
    alb_sg_id                  = "sg-alb-999"
    ecs_api_sg_id              = "sg-api-999"
    ecs_consumer_sg_id         = "sg-consumer-999"
    ecs_generator_sg_id        = "sg-generator-999"
    redis_sg_id                = "sg-redis-999"
    chromadb_sg_id             = "sg-chromadb-999"
    ecs_execution_role_arn     = "arn:aws:iam::999999999999:role/test-ecs-execution-role"
    ecs_task_role_arn          = "arn:aws:iam::999999999999:role/test-ecs-task-role"
    ecr_repository_url         = "999999999999.dkr.ecr.us-east-1.amazonaws.com/test-app"
    kafka_bootstrap_servers    = "10.0.9.100:9092"
    rds_endpoint               = "test-postgres.999999999999.us-east-1.rds.amazonaws.com:5432"
    rds_port                   = "5432"
    rds_db_name                = "test_db"
    db_master_secret_arn       = "arn:aws:secretsmanager:us-east-1:999999999999:secret:test/db/master"
    jwt_secret_arn             = "arn:aws:secretsmanager:us-east-1:999999999999:secret:test/jwt"
    sagemaker_secret_arn       = "arn:aws:secretsmanager:us-east-1:999999999999:secret:test/sagemaker"
    mlflow_tracking_secret_arn = "arn:aws:secretsmanager:us-east-1:999999999999:secret:test/mlflow"
    rag_ollama_secret_arn      = "arn:aws:secretsmanager:us-east-1:999999999999:secret:test/rag-ollama"
    cors_origins               = "https://test.example.com"
  }
  assert {
    condition     = var.project_name == "test-ecs"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "staging"
    error_message = "environment must be overridable"
  }
}
