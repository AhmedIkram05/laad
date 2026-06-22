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

  user_data = base64encode(<<EOF
#!/bin/bash
set -euxo pipefail

# 1. Update system
dnf update -y

# 2. Install Java 17 (Amazon Corretto)
dnf install -y java-17-amazon-corretto-devel

# 3. Download Kafka 3.7.0
cd /opt
wget -q https://downloads.apache.org/kafka/3.7.0/kafka_2.13-3.7.0.tgz
tar -xzf kafka_2.13-3.7.0.tgz
ln -s kafka_2.13-3.7.0 kafka

# 4. Create Kafka data directory
mkdir -p /data/kafka
chown -R ec2-user:ec2-user /data/kafka

# 5. Configure KRaft (server.properties with process.roles=broker,controller)
cat > /opt/kafka/config/kraft/server.properties << 'KAFKA_EOF'
# KRaft mode - no Zookeeper
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@localhost:9093

# Listeners
listeners=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
advertised.listeners=PLAINTEXT://PRIVATE_IP:9092
listener.security.protocol.map=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT
inter.broker.listener.name=PLAINTEXT
controller.listener.names=CONTROLLER

# Logs
log.dirs=/data/kafka
num.partitions=3
default.replication.factor=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1

# Heap
KAFKA_HEAP_OPTS=-Xms512m -Xmx512m
KAFKA_EOF

# Replace PRIVATE_IP with actual private IP
PRIVATE_IP=$$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
sed -i "s/PRIVATE_IP/$$PRIVATE_IP/g" /opt/kafka/config/kraft/server.properties

# 6. Generate cluster ID and format the log directory
/opt/kafka/bin/kafka-storage.sh random-uuid > /tmp/kafka-cluster-id
/opt/kafka/bin/kafka-storage.sh format -t $$(cat /tmp/kafka-cluster-id) -c /opt/kafka/config/kraft/server.properties

# 7. Create systemd service
cat > /etc/systemd/system/kafka.service << 'SYSTEMD_EOF'
[Unit]
Description=Apache Kafka (KRaft mode)
After=network.target

[Service]
Type=simple
User=ec2-user
Environment="KAFKA_HEAP_OPTS=-Xms512m -Xmx512m"
ExecStart=/opt/kafka/bin/kafka-server-start.sh /opt/kafka/config/kraft/server.properties
ExecStop=/opt/kafka/bin/kafka-server-stop.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

# 8. Enable and start
systemctl daemon-reload
systemctl enable kafka
systemctl start kafka
EOF
  )

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

