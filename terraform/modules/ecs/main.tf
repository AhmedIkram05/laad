# LAAD ECS Module
# ECS cluster, 5 task definitions, 4 services, ALB, log groups,
# metric filters, and CloudWatch dashboard for production monitoring.

# ---------------------------------------------------------------------------
# ECS Cluster
# ---------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = "laad-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name        = "laad-cluster"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 1
    capacity_provider = "FARGATE"
  }

  default_capacity_provider_strategy {
    base              = 0
    weight            = 2
    capacity_provider = "FARGATE_SPOT"
  }
}

# ---------------------------------------------------------------------------
# CloudWatch Log Groups
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/laad-api"
  retention_in_days = 7

  tags = {
    Name        = "/ecs/laad-api"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_cloudwatch_log_group" "consumer" {
  name              = "/ecs/laad-consumer"
  retention_in_days = 7

  tags = {
    Name        = "/ecs/laad-consumer"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_cloudwatch_log_group" "generator" {
  name              = "/ecs/laad-generator"
  retention_in_days = 7

  tags = {
    Name        = "/ecs/laad-generator"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Task Definitions
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "api" {
  family                   = "laad-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 3072
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${var.ecr_repository_url}:api-latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/laad-api"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      environment = [
        { name = "LAAD_ENV", value = "production" },
        { name = "KAFKA_BOOTSTRAP_SERVERS", value = var.kafka_bootstrap_servers },
        { name = "POSTGRES_HOST", value = split(":", var.rds_endpoint)[0] },
        { name = "POSTGRES_PORT", value = tostring(var.rds_port) },
        { name = "POSTGRES_DB", value = var.rds_db_name },
        { name = "POSTGRES_USER", value = "laad_admin" },
        { name = "CORS_ORIGINS", value = var.cors_origins },
        { name = "AWS_REGION", value = var.aws_region },
      ]

      secrets = [
        { name = "JWT_SECRET_KEY", valueFrom = "${var.jwt_secret_arn}:JWT_SECRET_KEY::" },
        { name = "POSTGRES_PASSWORD", valueFrom = "${var.db_master_secret_arn}:password::" },
        { name = "SAGEMAKER_ENDPOINT_NAME", valueFrom = "${var.sagemaker_secret_arn}:SAGEMAKER_ENDPOINT_NAME::" },
        { name = "MLFLOW_TRACKING_URI", valueFrom = "${var.mlflow_tracking_secret_arn}:MLFLOW_TRACKING_URI::" },
        { name = "MLFLOW_S3_ARTIFACT_ROOT", valueFrom = "${var.mlflow_tracking_secret_arn}:MLFLOW_S3_ARTIFACT_ROOT::" },
        { name = "OLLAMA_API_KEY", valueFrom = "${var.rag_ollama_secret_arn}:OLLAMA_API_KEY::" },
        { name = "OPENROUTER_API_KEY", valueFrom = "${var.rag_ollama_secret_arn}:OPENROUTER_API_KEY::" },
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name        = "laad-api"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_task_definition" "consumer" {
  family                   = "laad-consumer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name      = "consumer"
      image     = "${var.ecr_repository_url}:consumer-latest"
      essential = true

      command = ["python", "-m", "backend.kafka.consumer"]

      portMappings = [
        {
          containerPort = 8081
          protocol      = "tcp"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/laad-consumer"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "consumer"
        }
      }

      environment = [
        { name = "LAAD_ENV", value = "production" },
        { name = "KAFKA_BOOTSTRAP_SERVERS", value = var.kafka_bootstrap_servers },
        { name = "POSTGRES_HOST", value = split(":", var.rds_endpoint)[0] },
        { name = "POSTGRES_PORT", value = tostring(var.rds_port) },
        { name = "POSTGRES_DB", value = var.rds_db_name },
        { name = "POSTGRES_USER", value = "laad_admin" },
      ]

      secrets = [
        { name = "POSTGRES_PASSWORD", valueFrom = "${var.db_master_secret_arn}:password::" },
        { name = "JWT_SECRET_KEY", valueFrom = "${var.jwt_secret_arn}:JWT_SECRET_KEY::" },
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8081/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name        = "laad-consumer"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_task_definition" "generator" {
  family                   = "laad-generator"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = var.ecs_execution_role_arn

  container_definitions = jsonencode([
    {
      name      = "generator"
      image     = "${var.ecr_repository_url}:generator-latest"
      essential = true

      command = ["python", "-m", "backend.generator.continuous_generator"]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/laad-generator"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "generator"
        }
      }

      environment = [
        { name = "KAFKA_BOOTSTRAP_SERVERS", value = var.kafka_bootstrap_servers },
        { name = "LAAD_ENV", value = "production" },
        { name = "POSTGRES_HOST", value = split(":", var.rds_endpoint)[0] },
        { name = "POSTGRES_PORT", value = tostring(var.rds_port) },
        { name = "POSTGRES_DB", value = var.rds_db_name },
        { name = "POSTGRES_USER", value = "laad_admin" },
      ]

      secrets = [
        { name = "POSTGRES_PASSWORD", valueFrom = "${var.db_master_secret_arn}:password::" },
      ]
    }
  ])

  tags = {
    Name        = "laad-generator"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_task_definition" "redis" {
  family                   = "laad-redis"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = var.ecs_execution_role_arn

  container_definitions = jsonencode([
    {
      name      = "redis"
      image     = "redis:7-alpine"
      essential = true

      portMappings = [
        {
          containerPort = 6379
          protocol      = "tcp"
        }
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "redis-cli ping || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  ])

  tags = {
    Name        = "laad-redis"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_task_definition" "chromadb" {
  family                   = "laad-chromadb"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = var.ecs_execution_role_arn

  container_definitions = jsonencode([
    {
      name      = "chromadb"
      image     = "chromadb/chroma:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "IS_PERSISTENT", value = "TRUE" },
        { name = "PERSIST_DIRECTORY", value = "/chroma/chroma-data" },
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name        = "laad-chromadb"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Application Load Balancer
# ---------------------------------------------------------------------------

resource "aws_lb" "main" {
  name                       = "laad-alb"
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [var.alb_sg_id]
  subnets                    = var.public_subnet_ids
  enable_deletion_protection = false
  idle_timeout               = 60

  tags = {
    Name        = "laad-alb"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_lb_target_group" "api" {
  name        = "laad-api-tg"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path                = "/health"
    port                = 8000
    protocol            = "HTTP"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200-399"
  }

  tags = {
    Name        = "laad-api-tg"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_lb_listener" "main" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  tags = {
    Name        = "laad-alb-listener"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# ECS Services
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "api" {
  name            = "laad-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_api_sg_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.main]

  tags = {
    Name        = "laad-api"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_service" "consumer" {
  name            = "laad-consumer"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.consumer.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_consumer_sg_id]
    assign_public_ip = false
  }

  tags = {
    Name        = "laad-consumer"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_service" "generator" {
  name            = "laad-generator"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.generator.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_generator_sg_id]
    assign_public_ip = false
  }

  tags = {
    Name        = "laad-generator"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_service" "redis" {
  name            = "laad-redis"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.redis.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.redis_sg_id]
    assign_public_ip = false
  }

  tags = {
    Name        = "laad-redis"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_ecs_service" "chromadb" {
  name            = "laad-chromadb"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.chromadb.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.chromadb_sg_id]
    assign_public_ip = false
  }

  tags = {
    Name        = "laad-chromadb"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# CloudWatch Metric Filters
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_metric_filter" "api_errors" {
  name           = "APIErrorCount"
  pattern        = "ERROR"
  log_group_name = aws_cloudwatch_log_group.api.name

  metric_transformation {
    name      = "APIErrorCount"
    namespace = "LAAD"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "consumer_errors" {
  name           = "ConsumerErrorCount"
  pattern        = "ERROR"
  log_group_name = aws_cloudwatch_log_group.consumer.name

  metric_transformation {
    name      = "ConsumerErrorCount"
    namespace = "LAAD"
    value     = "1"
  }
}

# ---------------------------------------------------------------------------
# CloudWatch Dashboard
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "laad-dashboard-production"

  dashboard_body = jsonencode({
    widgets = [
      # Widget 1: ALB Request Count
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            [
              "AWS/ApplicationELB",
              "RequestCount",
              "LoadBalancer",
              aws_lb.main.arn_suffix,
              { stat = "Sum" },
            ]
          ]
          period         = 300
          stat           = "Sum"
          region         = var.aws_region
          title          = "ALB Request Count"
          view           = "timeSeries"
          stacked        = false
          periodOverride = "inherit"
        }
      },
      # Widget 2: ALB Target Response Time
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            [
              "AWS/ApplicationELB",
              "TargetResponseTime",
              "LoadBalancer",
              aws_lb.main.arn_suffix,
              { stat = "Average" },
            ]
          ]
          period         = 300
          stat           = "Average"
          region         = var.aws_region
          title          = "ALB Target Response Time"
          view           = "timeSeries"
          stacked        = false
          periodOverride = "inherit"
        }
      },
      # Widget 3: ECS API CPU + Memory + LAAD API Errors
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            [
              "AWS/ECS",
              "CPUUtilization",
              "ClusterName",
              aws_ecs_cluster.main.name,
              "ServiceName",
              aws_ecs_service.api.name,
              { stat = "Average" },
            ],
            [
              "AWS/ECS",
              "MemoryUtilization",
              "ClusterName",
              aws_ecs_cluster.main.name,
              "ServiceName",
              aws_ecs_service.api.name,
              { stat = "Average" },
            ],
            [
              "LAAD",
              "APIErrorCount",
              { stat = "Sum" },
            ],
          ]
          period         = 300
          stat           = "Average"
          region         = var.aws_region
          title          = "ECS API - CPU / Memory / Errors"
          view           = "timeSeries"
          stacked        = false
          periodOverride = "inherit"
        }
      },
      # Widget 4: ECS Consumer CPU + Memory + LAAD Consumer Errors
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            [
              "AWS/ECS",
              "CPUUtilization",
              "ClusterName",
              aws_ecs_cluster.main.name,
              "ServiceName",
              aws_ecs_service.consumer.name,
              { stat = "Average" },
            ],
            [
              "AWS/ECS",
              "MemoryUtilization",
              "ClusterName",
              aws_ecs_cluster.main.name,
              "ServiceName",
              aws_ecs_service.consumer.name,
              { stat = "Average" },
            ],
            [
              "LAAD",
              "ConsumerErrorCount",
              { stat = "Sum" },
            ],
          ]
          period         = 300
          stat           = "Average"
          region         = var.aws_region
          title          = "ECS Consumer - CPU / Memory / Errors"
          view           = "timeSeries"
          stacked        = false
          periodOverride = "inherit"
        }
      },
      # Widget 5: NAT Gateway Bytes
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6

        properties = {
          metrics = [
            [
              "AWS/NATGateway",
              "BytesOutToDestination",
              { stat = "Sum" },
            ],
            [
              "AWS/NATGateway",
              "BytesInFromDestination",
              { stat = "Sum" },
            ],
          ]
          period         = 300
          stat           = "Sum"
          region         = var.aws_region
          title          = "NAT Gateway Traffic"
          view           = "timeSeries"
          stacked        = false
          periodOverride = "inherit"
        }
      },
      # Widget 6: Kafka EC2 CPU + Status Check
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6

        properties = {
          metrics = [
            [
              "AWS/EC2",
              "CPUUtilization",
              { stat = "Average" },
            ],
            [
              "AWS/EC2",
              "StatusCheckFailed",
              { stat = "Average" },
            ],
          ]
          period         = 300
          stat           = "Average"
          region         = var.aws_region
          title          = "Kafka EC2 - CPU / Status Check"
          view           = "timeSeries"
          stacked        = false
          periodOverride = "inherit"
        }
      },
    ]
  })
}
