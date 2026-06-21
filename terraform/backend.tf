# Terraform S3 Remote State Backend
# Created after bootstrap — S3 bucket and DynamoDB table must exist first

terraform {
  backend "s3" {
    bucket       = "laad-terraform-state-ahmedikram"
    key          = "laad/terraform.tfstate"
    region       = "eu-west-2"
    use_lockfile = true
    encrypt      = true
  }
}
