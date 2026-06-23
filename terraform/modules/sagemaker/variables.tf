# SageMaker Module Variables

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "sagemaker_execution_role_arn" {
  description = "ARN of the SageMaker execution role"
  type        = string
}

variable "sagemaker_enabled" {
  description = "Whether SageMaker resources are created"
  type        = bool
}

variable "inference_image" {
  description = "SageMaker inference container image URI (AWS XGBoost image varies by region)"
  type        = string
  default     = "764974769150.dkr.ecr.eu-west-2.amazonaws.com/sagemaker-xgboost:1.7-1"
}

variable "model_data_url" {
  description = "S3 URI to the model artifact (e.g., s3://laad-mlflow-artifacts/sagemaker-models/1/model.tar.gz)"
  type        = string
  default     = ""
}

variable "instance_type" {
  description = "SageMaker endpoint instance type"
  type        = string
  default     = "ml.t2.medium"
}

variable "initial_instance_count" {
  description = "Initial instance count for the SageMaker endpoint"
  type        = number
  default     = 1
}
