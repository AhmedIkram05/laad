mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
      arn        = "arn:aws:iam::123456789012:user/test-user"
      user_id    = "AIDA1234567890EXAMPLE"
    }
  }
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"cloudfront.amazonaws.com\"},\"Action\":\"s3:GetObject\",\"Resource\":\"arn:aws:s3:::laad-frontend-123456789012/*\"}]}"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      id                          = "laad-frontend-123456789012"
      arn                         = "arn:aws:s3:::laad-frontend-123456789012"
      bucket_regional_domain_name = "laad-frontend-123456789012.s3.eu-west-2.amazonaws.com"
    }
  }
  mock_resource "aws_s3_bucket_versioning" {
    defaults = { id = "laad-frontend-123456789012" }
  }
  mock_resource "aws_s3_bucket_public_access_block" {
    defaults = { id = "laad-frontend-123456789012" }
  }
  mock_resource "aws_cloudfront_origin_access_control" {
    defaults = {
      id   = "E3ABCDEFGHIJKL"
      etag = "E3ABCDEFGHIJKL"
    }
  }
  mock_resource "aws_cloudfront_function" {
    defaults = {
      id          = "laad-production-api-path-rewrite"
      arn         = "arn:aws:cloudfront::123456789012:function/laad-production-api-path-rewrite"
      etag        = "ETABCDEFGHIJKL"
      live_stage_etag = "ETABCDEFGHIJKL"
    }
  }
  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      id          = "E1ABCDEFGHIJKL"
      arn         = "arn:aws:cloudfront::123456789012:distribution/E1ABCDEFGHIJKL"
      domain_name = "d1234567890abcdef.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
      etag        = "E3ABCDEFGHIJKL"
      last_modified_time = "2025-01-01T00:00:00Z"
      in_progress_validation_batches = 0
      caller_reference = "test-ref"
      status      = "Deployed"
    }
  }
  mock_resource "aws_s3_bucket_policy" {
    defaults = { id = "laad-frontend-123456789012" }
  }
}

variables {
  project_name = "laad"
  environment  = "production"
  alb_dns_name = "laad-alb-1234567890.eu-west-2.elb.amazonaws.com"
}

run "test_frontend_variables_plan" {
  command = plan
  assert {
    condition     = var.project_name == "laad"
    error_message = "Default project_name must be 'laad'"
  }
  assert {
    condition     = var.environment == "production"
    error_message = "Default environment must be 'production'"
  }
  assert {
    condition     = can(var.alb_dns_name)
    error_message = "alb_dns_name variable must be present"
  }
}

run "test_frontend_outputs_apply" {
  command = apply
  assert {
    condition     = can(module.frontend.s3_bucket_name)
    error_message = "Frontend module: s3_bucket_name output must be present"
  }
  assert {
    condition     = can(module.frontend.s3_bucket_arn)
    error_message = "Frontend module: s3_bucket_arn output must be present"
  }
  assert {
    condition     = can(module.frontend.cloudfront_distribution_id)
    error_message = "Frontend module: cloudfront_distribution_id output must be present"
  }
  assert {
    condition     = can(module.frontend.cloudfront_domain_name)
    error_message = "Frontend module: cloudfront_domain_name output must be present"
  }
  assert {
    condition     = can(module.frontend.cloudfront_distribution_arn)
    error_message = "Frontend module: cloudfront_distribution_arn output must be present"
  }
}

run "test_frontend_variable_overrides" {
  command = plan
  variables {
    project_name = "test-frontend"
    environment  = "staging"
    alb_dns_name = "test-alb-9999999999.us-east-1.elb.amazonaws.com"
  }
  assert {
    condition     = var.project_name == "test-frontend"
    error_message = "project_name must be overridable"
  }
  assert {
    condition     = var.environment == "staging"
    error_message = "environment must be overridable"
  }
}
