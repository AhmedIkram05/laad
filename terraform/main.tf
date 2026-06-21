# LAAD Root Terraform Module
# Modules are added per batch — this file is populated incrementally

# Batch 1a: VPC module
module "vpc" {
  source = "./modules/vpc"

  vpc_cidr           = var.vpc_cidr
  environment        = var.environment
  project_name       = var.project_name
  availability_zones = var.availability_zones
  aws_region         = var.aws_region
}

# Batch 1a: IAM module
module "iam" {
  source = "./modules/iam"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
}

# Batch 1a: ECR module
module "ecr" {
  source = "./modules/ecr"

  project_name = var.project_name
  environment  = var.environment
}

# Batch 1a: Secrets module
module "secrets" {
  source = "./modules/secrets"

  project_name = var.project_name
  environment  = var.environment
}

# Batch 2a: RDS module
module "rds" {
  source = "./modules/rds"

  project_name       = var.project_name
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  rds_sg_id          = module.vpc.rds_sg_id
}

# Batch 2a: EC2 Kafka module
module "kafka" {
  source = "./modules/kafka"

  project_name     = var.project_name
  environment      = var.environment
  public_subnet_id = module.vpc.public_subnet_ids[0]
  kafka_sg_id      = module.vpc.kafka_sg_id
}

# Batch 2a: ECS module
module "ecs" {
  source = "./modules/ecs"

  project_name               = var.project_name
  environment                = var.environment
  vpc_id                     = module.vpc.vpc_id
  public_subnet_ids          = module.vpc.public_subnet_ids
  private_subnet_ids         = module.vpc.private_subnet_ids
  alb_sg_id                  = module.vpc.alb_sg_id
  ecs_api_sg_id              = module.vpc.ecs_api_sg_id
  ecs_consumer_sg_id         = module.vpc.ecs_consumer_sg_id
  ecs_generator_sg_id        = module.vpc.ecs_generator_sg_id
  redis_sg_id                = module.vpc.redis_sg_id
  chromadb_sg_id             = module.vpc.chromadb_sg_id
  ecs_execution_role_arn     = module.iam.ecs_execution_role_arn
  ecs_task_role_arn          = module.iam.ecs_task_role_arn
  ecr_repository_url         = module.ecr.repository_url
  kafka_bootstrap_servers    = "${module.kafka.kafka_private_ip}:9092"
  rds_endpoint               = module.rds.rds_endpoint
  rds_port                   = module.rds.rds_port
  rds_db_name                = module.rds.rds_db_name
  db_master_secret_arn       = module.rds.db_master_secret_arn
  jwt_secret_arn             = module.secrets.jwt_secret_arn
  sagemaker_secret_arn       = module.secrets.sagemaker_secret_arn
  mlflow_tracking_secret_arn = module.secrets.mlflow_secret_arn
  rag_ollama_secret_arn      = module.secrets.rag_ollama_secret_arn
  aws_region                 = var.aws_region
  cors_origins               = "http://localhost:5173"
}

# Batch 2a: Frontend infra module (S3 + CloudFront)
module "frontend" {
  source = "./modules/frontend"

  project_name = var.project_name
  environment  = var.environment
}

# Batch 2a: Monitoring module (budget alerts + alarms)
module "monitoring" {
  source = "./modules/monitoring"

  project_name = var.project_name
  environment  = var.environment
}

# Batch 3: SageMaker module will be added here (gated by sagemaker_enabled)
