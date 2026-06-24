# LAAD ECR Repository
# Stores api, consumer, and generator Docker images

# checkov:skip=CKV_AWS_136:KMS encryption not required for dev ECR repository
# checkov:skip=CKV_AWS_51:Mutable image tags acceptable for dev workflow
resource "aws_ecr_repository" "app" {
  name                 = "${var.project_name}-app"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "${var.project_name}-app"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Exclude api-latest, consumer-latest, and generator-latest tags from pruning"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["api-latest", "consumer-latest", "generator-latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 99999
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep only the 25 most recent images (tagged + untagged)"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 25
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
