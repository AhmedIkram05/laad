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
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test-role" }
  }
  mock_resource "aws_iam_role_policy" {
    defaults = { id = "test-policy" }
  }
  mock_resource "aws_iam_role_policy_attachment" {
    defaults = { id = "test-attachment" }
  }
  mock_resource "aws_ecr_repository" {
    defaults = { repository_url = "test-url", arn = "test-arn" }
  }
  mock_resource "aws_ecr_lifecycle_policy" {
    defaults = { id = "test" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:test:secret" }
  }
  mock_resource "aws_secretsmanager_secret_version" {
    defaults = { id = "test" }
  }
  mock_resource "random_password" {
    defaults = { result = "test-password" }
  }
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
  mock_resource "aws_db_instance" { defaults = { id = "db-12345", endpoint = "test.rds.amazonaws.com", port = 5432, db_name = "test_db", address = "test.rds.amazonaws.com" } }
  mock_resource "aws_db_subnet_group" { defaults = { id = "test" } }
  mock_resource "aws_db_parameter_group" { defaults = { id = "test" } }
  mock_data "aws_secretsmanager_secret" { defaults = { arn = "arn:aws:secretsmanager:test:secret" } }
  mock_resource "aws_instance" { defaults = { id = "i-12345", private_ip = "10.0.0.1" } }
  mock_data "aws_ami" { defaults = { id = "ami-12345", image_id = "ami-12345", name = "test-ami", owner_id = "12345" } }

  mock_resource "aws_ecs_cluster" { defaults = { id = "arn:ecs:cluster", name = "test" } }
  mock_resource "aws_ecs_cluster_capacity_providers" { defaults = { id = "test" } }
  mock_resource "aws_ecs_service" { defaults = { id = "arn:ecs:service" } }
  mock_resource "aws_ecs_task_definition" { defaults = { id = "arn:ecs:td", arn = "arn:ecs:td" } }
  mock_resource "aws_lb" { defaults = { id = "arn:lb", arn = "arn:lb", dns_name = "test.elb.amazonaws.com", zone_id = "Z123" } }
  mock_resource "aws_lb_listener" { defaults = { id = "arn:listener" } }
  mock_resource "aws_lb_target_group" { defaults = { id = "arn:tg", arn = "arn:tg" } }
  mock_resource "aws_cloudwatch_dashboard" { defaults = { id = "test" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { id = "test", arn = "arn:log" } }
  mock_resource "aws_cloudwatch_log_metric_filter" { defaults = { id = "test" } }
  mock_resource "aws_service_discovery_private_dns_namespace" { defaults = { id = "test" } }
  mock_resource "aws_service_discovery_service" { defaults = { id = "test" } }
  mock_resource "aws_s3_bucket" { defaults = { id = "test-bucket", arn = "arn:s3", bucket = "test-bucket" } }
  mock_resource "aws_s3_bucket_ownership_controls" { defaults = { id = "test" } }
  mock_resource "aws_s3_bucket_public_access_block" { defaults = { id = "test" } }
  mock_resource "aws_s3_object" { defaults = { id = "test" } }
  mock_resource "aws_cloudfront_distribution" { defaults = { id = "E12345", arn = "arn:cf", domain_name = "test.cloudfront.net" } }
  mock_resource "aws_cloudfront_origin_access_control" { defaults = { id = "test" } }
  mock_resource "aws_cloudfront_origin_access_identity" { defaults = { id = "test" } }
  mock_resource "aws_sns_topic" { defaults = { id = "test-topic", arn = "arn:sns" } }
  mock_resource "aws_sns_topic_policy" { defaults = { id = "test" } }
  mock_resource "aws_cloudwatch_metric_alarm" { defaults = { id = "test-alarm", arn = "arn:alarm" } }
  mock_resource "aws_sagemaker_endpoint" { defaults = { id = "test", arn = "arn:sm", name = "test" } }
  mock_resource "aws_sagemaker_endpoint_configuration" { defaults = { id = "test" } }
  mock_resource "aws_sagemaker_model" { defaults = { id = "test", arn = "arn:sm:model" } }
}

run "test_apply_outputs" {
  command = apply

  assert {
    condition     = module.iam.ecs_execution_role_arn == "arn:aws:iam::123456789012:role/test-role"
    error_message = "IAM role ARN should match mock default"
  }
  assert {
    condition     = module.ecr.repository_url == "test-url"
    error_message = "ECR URL should match mock default"
  }
}
