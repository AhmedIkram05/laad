# LAAD Kafka EC2 Module
# Provisions a single EC2 instance running Apache Kafka in KRaft mode
# (no Zookeeper). Uses a static Elastic IP for stable addressing.
# The kafka_sg security group is created by the VPC module and passed in
# as var.kafka_sg_id - only security group rules are managed here.

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-arm64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ---------------------------------------------------------------------------
# EC2 Kafka Instance (KRaft mode - no Zookeeper)
# ---------------------------------------------------------------------------

resource "aws_instance" "kafka" {
  ami                         = data.aws_ami.amazon_linux_2023.id
  instance_type               = "t4g.small"
  subnet_id                   = var.public_subnet_id
  vpc_security_group_ids      = [var.kafka_sg_id]
  associate_public_ip_address = true
  key_name                    = null

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  user_data = file("${path.module}/user-data.sh")

  tags = {
    Name        = "laad-kafka"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Elastic IP for Kafka (stable addressing)
# ---------------------------------------------------------------------------

resource "aws_eip" "kafka" {
  domain   = "vpc"
  instance = aws_instance.kafka.id

  tags = {
    Name        = "laad-kafka-eip"
    Environment = var.environment
    Project     = var.project_name
  }
}

