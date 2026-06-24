terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "project_name"               { type = string }
variable "environment"                { type = string }
variable "vpc_id"                     { type = string }
variable "public_subnet_ids"          { type = list(string) }
variable "private_subnet_ids"         { type = list(string) }
variable "alb_sg_id"                  { type = string }
variable "ecs_api_sg_id"              { type = string }
variable "ecs_consumer_sg_id"         { type = string }
variable "ecs_generator_sg_id"        { type = string }
variable "redis_sg_id"                { type = string }
variable "chromadb_sg_id"             { type = string }
variable "ecs_execution_role_arn"     { type = string }
variable "ecs_task_role_arn"          { type = string }
variable "ecr_repository_url"         { type = string }
variable "kafka_bootstrap_servers"    { type = string }
variable "rds_endpoint"               { type = string }
variable "rds_port"                   { type = string }
variable "rds_db_name"                { type = string }
variable "db_master_secret_arn"       { type = string }
variable "jwt_secret_arn"             { type = string }
variable "sagemaker_secret_arn"       { type = string }
variable "mlflow_tracking_secret_arn" { type = string }
variable "rag_ollama_secret_arn"      { type = string }
variable "aws_region"                 { type = string }
variable "cors_origins"               { type = string }

module "ecs" {
  source = "../../../modules/ecs"

  project_name               = var.project_name
  environment                = var.environment
  vpc_id                     = var.vpc_id
  public_subnet_ids          = var.public_subnet_ids
  private_subnet_ids         = var.private_subnet_ids
  alb_sg_id                  = var.alb_sg_id
  ecs_api_sg_id              = var.ecs_api_sg_id
  ecs_consumer_sg_id         = var.ecs_consumer_sg_id
  ecs_generator_sg_id        = var.ecs_generator_sg_id
  redis_sg_id                = var.redis_sg_id
  chromadb_sg_id             = var.chromadb_sg_id
  ecs_execution_role_arn     = var.ecs_execution_role_arn
  ecs_task_role_arn          = var.ecs_task_role_arn
  ecr_repository_url         = var.ecr_repository_url
  kafka_bootstrap_servers    = var.kafka_bootstrap_servers
  rds_endpoint               = var.rds_endpoint
  rds_port                   = var.rds_port
  rds_db_name                = var.rds_db_name
  db_master_secret_arn       = var.db_master_secret_arn
  jwt_secret_arn             = var.jwt_secret_arn
  sagemaker_secret_arn       = var.sagemaker_secret_arn
  mlflow_tracking_secret_arn = var.mlflow_tracking_secret_arn
  rag_ollama_secret_arn      = var.rag_ollama_secret_arn
  aws_region                 = var.aws_region
  cors_origins               = var.cors_origins
}

output "ecs_cluster_name" { value = module.ecs.ecs_cluster_name }
output "ecs_cluster_id"   { value = module.ecs.ecs_cluster_id }
output "alb_arn"          { value = module.ecs.alb_arn }
output "alb_dns_name"     { value = module.ecs.alb_dns_name }
output "alb_zone_id"      { value = module.ecs.alb_zone_id }
output "target_group_arn" { value = module.ecs.target_group_arn }
