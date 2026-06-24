# ---------------------------------------------------------------------------
# SageMaker Module — XGBoost model endpoint for anomaly detection
# ---------------------------------------------------------------------------
# Creates a SageMaker model, endpoint configuration, and real-time endpoint
# for AI/ML-powered anomaly scoring. All resources are gated by
# var.sagemaker_enabled — the entire module is instantiated only when
# sagemaker_enabled is true (via count in root main.tf).
# ---------------------------------------------------------------------------

locals {
  create = var.sagemaker_enabled ? 1 : 0
}

# ===========================================================================
# SageMaker Model
# ===========================================================================
# Points to an XGBoost inference container and the S3 model artifact
# uploaded by the model upload ECS run-task.

resource "aws_sagemaker_model" "champion" {
  count                    = local.create
  name                     = "${var.project_name}-xgb-champion"
  execution_role_arn       = var.sagemaker_execution_role_arn
  enable_network_isolation = true

  primary_container {
    image          = var.inference_image
    model_data_url = var.model_data_url
  }

  tags = {
    Name        = "${var.project_name}-xgb-champion"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ===========================================================================
# SageMaker Endpoint Configuration
# ===========================================================================
# Single-variant config: ml.m5.large, 1 instance. Scales to zero via
# scheduled stop/start (EventBridge Scheduler) for cost management.

# checkov:skip=CKV_AWS_98:SageMaker endpoint uses instance-based encryption; KMS not configured for dev
resource "aws_sagemaker_endpoint_configuration" "champion" {
  count = local.create
  name  = "${var.project_name}-xgb-champion-config"

  production_variants {
    variant_name           = "champion"
    model_name             = aws_sagemaker_model.champion[0].name
    initial_instance_count = var.initial_instance_count
    instance_type          = var.instance_type
    initial_variant_weight = 1
  }

  tags = {
    Name        = "${var.project_name}-xgb-champion-config"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ===========================================================================
# SageMaker Endpoint
# ===========================================================================
# Real-time endpoint for anomaly predictions. The endpoint name is
# propagated to the laad/sagemaker Secrets Manager secret post-deploy
# so the backend can discover it dynamically.

resource "aws_sagemaker_endpoint" "champion" {
  count                = local.create
  name                 = "${var.project_name}-xgb-champion"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.champion[0].name

  tags = {
    Name        = "${var.project_name}-xgb-champion"
    Environment = var.environment
    Project     = var.project_name
  }
}
