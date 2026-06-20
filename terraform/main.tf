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

# Batch 2a: RDS, EC2 Kafka, ECS, Frontend, Monitoring modules will be added here
# Batch 3: SageMaker module will be added here (gated by sagemaker_enabled)
