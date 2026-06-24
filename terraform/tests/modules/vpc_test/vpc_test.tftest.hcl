mock_provider "aws" {
  mock_resource "aws_vpc" {
    defaults = { id = "vpc-12345" }
  }
  mock_resource "aws_subnet" {
    defaults = { id = "subnet-12345" }
  }
  mock_resource "aws_internet_gateway" {
    defaults = { id = "igw-12345" }
  }
  mock_resource "aws_eip" {
    defaults = {
      id        = "eip-12345"
      public_ip = "1.2.3.4"
    }
  }
  mock_resource "aws_nat_gateway" {
    defaults = {
      id        = "nat-12345"
      public_ip = "5.6.7.8"
    }
  }
  mock_resource "aws_route_table" {
    defaults = { id = "rtb-12345" }
  }
  mock_resource "aws_route_table_association" {
    defaults = { id = "rtba-12345" }
  }
  mock_resource "aws_vpc_endpoint" {
    defaults = { id = "vpce-12345" }
  }
  mock_resource "aws_security_group" {
    defaults = { id = "sg-12345" }
  }
  mock_resource "aws_security_group_rule" {
    defaults = { id = "sgr-12345" }
  }
}

variables {
  project_name       = "laad"
  environment        = "production"
  vpc_cidr           = "10.0.0.0/16"
  availability_zones = ["eu-west-2a", "eu-west-2b"]
  aws_region         = "eu-west-2"
}

run "test_vpc_variables_plan" {
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
    condition     = var.vpc_cidr == "10.0.0.0/16"
    error_message = "Default VPC CIDR must be 10.0.0.0/16"
  }
  assert {
    condition     = length(var.availability_zones) == 2
    error_message = "Must have exactly 2 availability zones"
  }
}

run "test_vpc_outputs_apply" {
  command = apply

  assert {
    condition     = module.vpc.vpc_id == "vpc-12345"
    error_message = "VPC module: vpc_id output must match mock default"
  }
  assert {
    condition     = length(module.vpc.public_subnet_ids) == 2
    error_message = "VPC module: must output 2 public subnet IDs"
  }
  assert {
    condition     = length(module.vpc.private_subnet_ids) == 2
    error_message = "VPC module: must output 2 private subnet IDs"
  }
  assert {
    condition     = module.vpc.alb_sg_id == "sg-12345"
    error_message = "VPC module: alb_sg_id output must match mock"
  }
  assert {
    condition     = module.vpc.ecs_api_sg_id == "sg-12345"
    error_message = "VPC module: ecs_api_sg_id output must match mock"
  }
  assert {
    condition     = module.vpc.ecs_consumer_sg_id == "sg-12345"
    error_message = "VPC module: ecs_consumer_sg_id output must match mock"
  }
  assert {
    condition     = module.vpc.ecs_generator_sg_id == "sg-12345"
    error_message = "VPC module: ecs_generator_sg_id output must match mock"
  }
  assert {
    condition     = module.vpc.rds_sg_id == "sg-12345"
    error_message = "VPC module: rds_sg_id output must match mock"
  }
  assert {
    condition     = module.vpc.kafka_sg_id == "sg-12345"
    error_message = "VPC module: kafka_sg_id output must match mock"
  }
  assert {
    condition     = module.vpc.redis_sg_id == "sg-12345"
    error_message = "VPC module: redis_sg_id output must match mock"
  }
  assert {
    condition     = module.vpc.chromadb_sg_id == "sg-12345"
    error_message = "VPC module: chromadb_sg_id output must match mock"
  }
  assert {
    condition     = module.vpc.nat_gateway_id == "nat-12345"
    error_message = "VPC module: nat_gateway_id output must match mock"
  }
  assert {
    condition     = module.vpc.nat_gateway_public_ip == "1.2.3.4"
    error_message = "VPC module: nat_gateway_public_ip output must match mock (from aws_eip)"
  }
}

run "test_vpc_variable_overrides" {
  command = plan

  variables {
    project_name = "test-vpc"
    environment  = "staging"
    vpc_cidr     = "172.16.0.0/16"
  }

  assert {
    condition     = var.project_name == "test-vpc"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "staging"
    error_message = "environment must be overridable"
  }
  assert {
    condition     = var.vpc_cidr == "172.16.0.0/16"
    error_message = "vpc_cidr must be overridable"
  }
}
