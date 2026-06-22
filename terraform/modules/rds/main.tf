# LAAD RDS Module
# PostgreSQL 16 RDS instance for the LAAD application database.
# Creates the DB instance, parameter group, subnet group, and updates the
# master secret in Secrets Manager (secret itself created by secrets module).

# ---------------------------------------------------------------------------
# Random password for the RDS master user
# ---------------------------------------------------------------------------

resource "random_password" "rds_master" {
  length  = 24
  special = false
}

# ---------------------------------------------------------------------------
# Secrets Manager — update LAAD app DB master credentials
# Secret "laad/db/master" is created by the secrets module (Batch 1a).
# This module only updates the secret version with the actual RDS values.
# ---------------------------------------------------------------------------

data "aws_secretsmanager_secret" "db_master" {
  name = "${var.project_name}/db/master"
}

resource "aws_secretsmanager_secret_version" "db_master" {
  secret_id = data.aws_secretsmanager_secret.db_master.id
  secret_string = jsonencode({
    username = "laad_admin"
    password = random_password.rds_master.result
    host     = aws_db_instance.main.endpoint
    port     = "5432"
    db_name  = "laad_db"
  })
}

# ---------------------------------------------------------------------------
# DB subnet group — places the RDS instance in the private subnets
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name        = "${var.project_name}-db-subnet-group-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# DB parameter group — PostgreSQL 16
# ---------------------------------------------------------------------------

resource "aws_db_parameter_group" "main" {
  family = "postgres16"
  name   = "laad-postgres16"

  tags = {
    Name        = "laad-postgres16"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# RDS instance — PostgreSQL 16, db.t4g.micro, gp3 storage
# ---------------------------------------------------------------------------

resource "aws_db_instance" "main" {
  identifier = "laad-postgres"

  engine         = "postgres"
  engine_version = "16.14"

  instance_class    = "db.t4g.micro"
  allocated_storage = 20
  storage_type      = "gp3"

  db_name  = "laad_db"
  username = "laad_admin"
  password = random_password.rds_master.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.rds_sg_id]
  parameter_group_name   = aws_db_parameter_group.main.name

  skip_final_snapshot = false
  deletion_protection = true

  auto_minor_version_upgrade = true
  backup_retention_period    = 1
  backup_window              = "03:00-04:00"
  maintenance_window         = "sun:04:00-sun:05:00"

  tags = {
    Name        = "laad-postgres"
    Environment = var.environment
    Project     = var.project_name
  }
}

# NOTE: Egress rule for the RDS security group is already defined in the VPC
# module (all SGs get full egress). No need to duplicate it here.
