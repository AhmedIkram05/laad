# ECS Module Variables

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "laad"
}

variable "environment" {
  description = "Deployment environment (production, staging)"
  type        = string
  default     = "production"
}

variable "vpc_id" {
  description = "VPC ID for the ALB target group and network configuration"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the ALB"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS Fargate tasks"
  type        = list(string)
}

variable "alb_sg_id" {
  description = "Security group ID for the ALB"
  type        = string
}

variable "ecs_api_sg_id" {
  description = "Security group ID for the ECS API service"
  type        = string
}

variable "ecs_consumer_sg_id" {
  description = "Security group ID for the ECS consumer service"
  type        = string
}

variable "ecs_generator_sg_id" {
  description = "Security group ID for the ECS log generator service"
  type        = string
}

variable "redis_sg_id" {
  description = "Security group ID for the Redis service"
  type        = string
}

variable "chromadb_sg_id" {
  description = "Security group ID for the ChromaDB service"
  type        = string
}

variable "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  type        = string
}

variable "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  type        = string
}

variable "ecr_repository_url" {
  description = "ECR repository URL for api, consumer, and generator images"
  type        = string
}

variable "kafka_bootstrap_servers" {
  description = "Kafka bootstrap servers (host:port)"
  type        = string
}

variable "rds_endpoint" {
  description = "RDS instance endpoint hostname"
  type        = string
}

variable "rds_port" {
  description = "RDS instance port"
  type        = number
}

variable "rds_db_name" {
  description = "RDS database name"
  type        = string
}

variable "db_master_secret_arn" {
  description = "ARN of the RDS master password secret"
  type        = string
}

variable "jwt_secret_arn" {
  description = "ARN of the JWT signing key secret"
  type        = string
}

variable "sagemaker_secret_arn" {
  description = "ARN of the SageMaker endpoint secret"
  type        = string
}

variable "mlflow_tracking_secret_arn" {
  description = "ARN of the MLflow tracking URI and config secret"
  type        = string
}

variable "rag_ollama_secret_arn" {
  description = "ARN of the RAG/Ollama API key secret"
  type        = string
}

variable "aws_region" {
  description = "AWS region for log groups and dashboard"
  type        = string
  default     = "eu-west-2"
}

variable "cors_origins" {
  description = "Comma-separated CORS allowed origins"
  type        = string
  default     = "http://localhost:5173,https://d123.cloudfront.net"
}
