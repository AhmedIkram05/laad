mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"ecs-tasks.amazonaws.com\"},\"Action\":\"sts:AssumeRole\"}]}"
    }
  }
  mock_data "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012", arn = "arn:aws:iam::123456789012:root", user_id = "test" }
  }
  mock_data "aws_secretsmanager_secret" { defaults = { arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test" } }
  mock_data "aws_ami" { defaults = { id = "ami-12345" } }

  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/test-role" } }
  mock_resource "aws_iam_role_policy" { defaults = { id = "test-policy" } }
  mock_resource "aws_iam_role_policy_attachment" { defaults = { id = "test-attachment" } }
  mock_resource "aws_ecr_repository" { defaults = { repository_url = "test-url", arn = "arn:aws:ecr:eu-west-2:123456789012:repository/test" } }
  mock_resource "aws_ecr_lifecycle_policy" { defaults = { id = "test" } }
  mock_resource "aws_secretsmanager_secret" { defaults = { arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:test" } }
  mock_resource "aws_secretsmanager_secret_version" { defaults = { id = "test" } }
  mock_resource "aws_vpc" { defaults = { id = "vpc-12345" } }
  mock_resource "aws_subnet" { defaults = { id = "subnet-12345" } }
  mock_resource "aws_internet_gateway" { defaults = { id = "igw-12345" } }
  mock_resource "aws_eip" { defaults = { id = "eip-12345", public_ip = "1.2.3.4" } }
  mock_resource "aws_nat_gateway" { defaults = { id = "nat-12345", public_ip = "1.2.3.4" } }
  mock_resource "aws_route_table" { defaults = { id = "rtb-12345" } }
  mock_resource "aws_route_table_association" { defaults = { id = "rtba-12345" } }
  mock_resource "aws_vpc_endpoint" { defaults = { id = "vpce-12345" } }
  mock_resource "aws_security_group" { defaults = { id = "sg-12345" } }
  mock_resource "aws_security_group_rule" { defaults = { id = "sgr-12345" } }
  mock_resource "aws_db_instance" { defaults = { id = "db-12345", endpoint = "test.rds.amazonaws.com", port = 5432, db_name = "test_db" } }
  mock_resource "aws_db_subnet_group" { defaults = { id = "test" } }
  mock_resource "aws_db_parameter_group" { defaults = { id = "test" } }
  mock_resource "aws_instance" { defaults = { id = "i-12345", private_ip = "10.0.0.1" } }
  mock_resource "aws_ecs_cluster" { defaults = { id = "arn:aws:ecs:eu-west-2:123456789012:cluster/test", name = "test" } }
  mock_resource "aws_ecs_cluster_capacity_providers" { defaults = { id = "test" } }
  mock_resource "aws_ecs_service" { defaults = { id = "arn:aws:ecs:eu-west-2:123456789012:service/test" } }
  mock_resource "aws_ecs_task_definition" { defaults = { id = "arn:aws:ecs:eu-west-2:123456789012:task-def/test", arn = "arn:aws:ecs:eu-west-2:123456789012:task-def/test" } }
  mock_resource "aws_lb" { defaults = { id = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:lb/test", arn = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:lb/test", dns_name = "test.elb.amazonaws.com", zone_id = "Z123" } }
  mock_resource "aws_lb_listener" { defaults = { id = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:listener/test" } }
  mock_resource "aws_lb_target_group" { defaults = { id = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:tg/test", arn = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:tg/test" } }
  mock_resource "aws_cloudwatch_dashboard" { defaults = { id = "test" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { id = "test", arn = "arn:aws:logs:eu-west-2:123456789012:log-group:test" } }
  mock_resource "aws_cloudwatch_log_metric_filter" { defaults = { id = "test" } }
  mock_resource "aws_service_discovery_private_dns_namespace" { defaults = { id = "test" } }
  mock_resource "aws_service_discovery_service" { defaults = { id = "test" } }
  mock_resource "aws_s3_bucket" { defaults = { id = "test-bucket", arn = "arn:aws:s3:::test-bucket" } }
  mock_resource "aws_s3_bucket_ownership_controls" { defaults = { id = "test" } }
  mock_resource "aws_s3_bucket_public_access_block" { defaults = { id = "test" } }
  mock_resource "aws_s3_object" { defaults = { id = "test" } }
  mock_resource "aws_cloudfront_distribution" { defaults = { id = "E12345", arn = "arn:aws:cloudfront::123456789012:distribution/E12345", domain_name = "test.cloudfront.net" } }
  mock_resource "aws_cloudfront_origin_access_control" { defaults = { id = "test" } }
  mock_resource "aws_cloudfront_origin_access_identity" { defaults = { id = "test" } }
  mock_resource "aws_sns_topic" { defaults = { id = "test-topic", arn = "arn:aws:sns:eu-west-2:123456789012:test-topic" } }
  mock_resource "aws_sns_topic_policy" { defaults = { id = "test" } }
  mock_resource "aws_cloudwatch_metric_alarm" { defaults = { id = "test-alarm", arn = "arn:aws:cloudwatch:eu-west-2:123456789012:alarm:test" } }
  mock_resource "aws_sagemaker_endpoint" { defaults = { id = "test", arn = "arn:aws:sagemaker:eu-west-2:123456789012:endpoint/test" } }
  mock_resource "aws_sagemaker_endpoint_configuration" { defaults = { id = "test" } }
  mock_resource "aws_sagemaker_model" { defaults = { id = "test", arn = "arn:aws:sagemaker:eu-west-2:123456789012:model/test" } }
}

run "test_apply_outputs" {
  command = apply

  assert {
    condition = module.iam.ecs_execution_role_arn != ""
    error_message = "IAM role ARN should be present"
  }
  assert {
    condition = module.iam.github_actions_role_arn != ""
    error_message = "GitHub Actions role ARN should be present"
  }
  assert {
    condition = module.vpc.vpc_id == "vpc-12345"
    error_message = "VPC ID should match mock"
  }
  assert {
    condition = module.vpc.alb_sg_id == "sg-12345"
    error_message = "SG ID should match mock"
  }
  assert {
    condition = length(module.vpc.public_subnet_ids) == 2
    error_message = "Should have 2 public subnets"
  }
  assert {
    condition = length(module.vpc.private_subnet_ids) == 2
    error_message = "Should have 2 private subnets"
  }
  assert {
    condition = module.ecr.repository_url != ""
    error_message = "ECR URL should be present"
  }
  assert {
    condition = module.monitoring.budget_sns_topic_arn == "arn:aws:sns:eu-west-2:123456789012:test-topic"
    error_message = "SNS topic ARN should match mock"
  }
  assert {
    condition = module.monitoring.rds_cpu_alarm_arn != ""
    error_message = "RDS alarm ARN should be present"
  }
}
