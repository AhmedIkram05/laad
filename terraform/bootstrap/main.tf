# LAAD Terraform State Backend Bootstrap
# Run once: terraform apply -auto-approve
# Creates S3 bucket for state storage and DynamoDB table for state locking

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "eu-west-2"
}

# S3 bucket for Terraform state storage
resource "aws_s3_bucket" "tf_state" {
  bucket = "laad-terraform-state-ahmedikram"
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Deny DeleteObject and DeleteObjectVersion unless MFA-authenticated
resource "aws_s3_bucket_policy" "tf_state_restrict" {
  bucket = aws_s3_bucket.tf_state.id
  policy = data.aws_iam_policy_document.tf_state_restrict.json
}

data "aws_iam_policy_document" "tf_state_restrict" {
  statement {
    effect = "Deny"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = [
      "s3:DeleteObject",
      "s3:DeleteObjectVersion"
    ]
    # Deny DeleteObject on all bucket objects EXCEPT the Terraform lock
    # file (.tflock). CI/CD pipelines need to create/delete lock files
    # during terraform plan/apply without MFA. State files (.tfstate)
    # remain fully MFA-protected.
    not_resources = [
      "${aws_s3_bucket.tf_state.arn}/laad/terraform.tfstate.tflock"
    ]
    condition {
      test     = "Bool"
      variable = "aws:MultiFactorAuthPresent"
      values   = ["false"]
    }
  }
}

# DynamoDB table for Terraform state locking
resource "aws_dynamodb_table" "tf_lock" {
  name         = "laad-terraform-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

output "state_bucket" {
  value = aws_s3_bucket.tf_state.id
}

output "lock_table" {
  value = aws_dynamodb_table.tf_lock.name
}
