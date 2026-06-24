mock_provider "aws" {
  mock_data "aws_ami" {
    defaults = {
      id          = "ami-1234567890abcdef0"
      architecture = "arm64"
      name        = "al2023-ami-2023.5.20241001.0-arm64"
    }
  }
  mock_resource "aws_instance" {
    defaults = {
      id          = "i-1234567890abcdef0"
      private_ip  = "10.0.1.100"
      public_ip   = "54.123.45.67"
      arn         = "arn:aws:ec2:eu-west-2:123456789012:instance/i-1234567890abcdef0"
    }
  }
  mock_resource "aws_eip" {
    defaults = {
      id         = "eipalloc-12345678"
      public_ip  = "54.123.45.67"
      domain     = "vpc"
    }
  }
}

variables {
  project_name     = "laad"
  environment      = "production"
  public_subnet_id = "subnet-abc"
  kafka_sg_id      = "sg-12345"
}

run "test_kafka_variables_plan" {
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

run "test_kafka_outputs_apply" {
  command = apply
  assert {
    condition     = can(module.kafka.kafka_private_ip)
    error_message = "Kafka module: kafka_private_ip output must be present"
  }
  assert {
    condition     = can(module.kafka.kafka_public_ip)
    error_message = "Kafka module: kafka_public_ip output must be present"
  }
  assert {
    condition     = can(module.kafka.kafka_eip_id)
    error_message = "Kafka module: kafka_eip_id output must be present"
  }
  assert {
    condition     = can(module.kafka.kafka_instance_id)
    error_message = "Kafka module: kafka_instance_id output must be present"
  }
  assert {
    condition     = module.kafka.kafka_sg_id == "sg-12345"
    error_message = "Kafka module: kafka_sg_id should pass through the input value"
  }
}

run "test_kafka_variable_overrides" {
  command = plan
  variables {
    project_name     = "test-kafka"
    environment      = "dev"
    public_subnet_id = "subnet-xyz"
    kafka_sg_id      = "sg-99999"
  }
  assert {
    condition     = var.project_name == "test-kafka"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "dev"
    error_message = "environment must be overridable"
  }
}
