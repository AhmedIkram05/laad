# LAAD Frontend Infrastructure
# S3 bucket for static hosting + CloudFront distribution with OAC

data "aws_caller_identity" "current" {}

locals {
  cloudfront_cache_policy_caching_disabled_id    = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  cloudfront_cache_policy_caching_optimized_id   = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  cloudfront_origin_request_policy_all_viewer_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
}

# S3 bucket for frontend static files
resource "aws_s3_bucket" "frontend" {
  bucket        = "${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}"
  force_destroy = false

  tags = {
    Name        = "laad-frontend"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Enable versioning for rollback capability
resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Block all public access — CloudFront OAC is the only way in
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Origin Access Control for CloudFront -> S3
resource "aws_cloudfront_origin_access_control" "main" {
  name                              = "laad-cloudfront-oac"
  description                       = "OAC for LAAD frontend S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "api_path_rewrite" {
  name    = "${var.project_name}-${var.environment}-api-path-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite frontend API paths to backend route prefixes"
  publish = true
  code    = <<-EOT
function handler(event) {
  var request = event.request;
  var uri = request.uri;

  if (hasPathPrefix(uri, '/api/insights')) {
    request.uri = '/api/analytics' + uri.substring('/api/insights'.length);
  } else if (hasPathPrefix(uri, '/api/rag') || hasPathPrefix(uri, '/api/analytics')) {
    request.uri = uri;
  } else if (uri === '/api') {
    request.uri = '/';
  } else if (uri.indexOf('/api/') === 0) {
    request.uri = uri.substring(4);
  }

  return request;
}

function hasPathPrefix(uri, prefix) {
  return uri === prefix || uri.indexOf(prefix + '/') === 0;
}
EOT
}

resource "aws_cloudfront_function" "spa_path_rewrite" {
  name    = "${var.project_name}-${var.environment}-spa-path-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Serve React SPA routes from index.html"
  publish = true
  code    = <<-EOT
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);

  if (uri === '/' || uri.slice(-1) === '/' || lastSegment.indexOf('.') === -1) {
    request.uri = '/index.html';
  }

  return request;
}
EOT
}

# CloudFront distribution serving the frontend
resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  comment             = "LAAD frontend distribution"
  default_root_object = "index.html"
  aliases             = []

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "S3Frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.main.id
  }

  # ALB origin for API requests (auth, admin, insights, health)
  origin {
    domain_name = var.alb_dns_name
    origin_id   = "ALB"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # API routes → ALB (no caching, forward all methods)
  ordered_cache_behavior {
    path_pattern     = "/auth/*"
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "ALB"
    compress         = true

    viewer_protocol_policy = "redirect-to-https"

    cache_policy_id          = local.cloudfront_cache_policy_caching_disabled_id
    origin_request_policy_id = local.cloudfront_origin_request_policy_all_viewer_id
  }

  ordered_cache_behavior {
    path_pattern     = "/api/*"
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "ALB"
    compress         = true

    viewer_protocol_policy = "redirect-to-https"

    cache_policy_id          = local.cloudfront_cache_policy_caching_disabled_id
    origin_request_policy_id = local.cloudfront_origin_request_policy_all_viewer_id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.api_path_rewrite.arn
    }
  }

  ordered_cache_behavior {
    path_pattern     = "/health*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "ALB"
    compress         = true

    viewer_protocol_policy = "redirect-to-https"

    cache_policy_id          = local.cloudfront_cache_policy_caching_disabled_id
    origin_request_policy_id = local.cloudfront_origin_request_policy_all_viewer_id
  }

  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3Frontend"

    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    cache_policy_id = local.cloudfront_cache_policy_caching_optimized_id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_path_rewrite.arn
    }
  }

  price_class      = "PriceClass_100"
  retain_on_delete = false

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name        = "laad-frontend"
    Environment = var.environment
    Project     = var.project_name
  }
}

# IAM policy document granting CloudFront OAC access to S3 objects
data "aws_iam_policy_document" "frontend_bucket_policy" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${aws_s3_bucket.frontend.id}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.main.arn]
    }
  }
}

# Attach the bucket policy
resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket_policy.json
}
