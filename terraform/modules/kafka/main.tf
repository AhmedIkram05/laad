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
# Log everything for debugging
exec > /var/log/user-data.log 2>&1
set -x

echo "=== Starting Kafka user_data at \$(date) ==="

# 1. Update system (skip if it takes too long — not critical for Kafka)
dnf update -y || echo "dnf update skipped (non-fatal)"

# 2. Install Java 17 (Amazon Corretto)
dnf install -y java-17-amazon-corretto-devel || echo "Java install failed (may already be installed)"
echo "Java version:"
java -version 2>&1 || echo "Java not available yet"

# 3. Download Kafka 3.7.0 (try multiple mirrors with retries)
cd /opt
KAFKA_TGZ="kafka_2.13-3.7.0.tgz"

download_kafka() {
    for url in \
        "https://archive.apache.org/dist/kafka/3.7.0/\$KAFKA_TGZ" \
        "https://dlcdn.apache.org/kafka/3.7.0/\$KAFKA_TGZ" \
        "https://downloads.apache.org/kafka/3.7.0/\$KAFKA_TGZ"; do
        for i in 1 2 3; do
            echo "Downloading Kafka from \$url (attempt \$i)..."
            if curl -fsSL "\$url" -o "\$KAFKA_TGZ"; then
                echo "Download successful from \$url"
                return 0
            fi
            sleep 3
        done
    done
    return 1
}

if [ ! -f "\$KAFKA_TGZ" ]; then
    download_kafka || echo "WARNING: All download attempts failed — will retry later"
fi

if [ -f "\$KAFKA_TGZ" ]; then
    tar -xzf "\$KAFKA_TGZ" && ln -sf kafka_2.13-3.7.0 kafka && echo "Kafka extracted to /opt/kafka"
else
    echo "Kafka download not available — skipping extraction"
fi

# 4. Create Kafka data directory
mkdir -p /data/kafka
chown -R ec2-user:ec2-user /data/kafka || true

# 5. Get private IP
PRIVATE_IP=\$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
echo "Private IP: \$PRIVATE_IP"

# 6. Configure KRaft server.properties (only if Kafka was extracted)
if [ -d /opt/kafka ]; then
    cat > /opt/kafka/config/kraft/server.properties << KAFKA_EOF
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@localhost:9093
listeners=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
advertised.listeners=PLAINTEXT://$${PRIVATE_IP}:9092
listener.security.protocol.map=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT
inter.broker.listener.name=PLAINTEXT
controller.listener.names=CONTROLLER
log.dirs=/data/kafka
num.partitions=3
default.replication.factor=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
KAFKA_EOF

    echo "server.properties:"
    grep -E "^(listeners|advertised)" /opt/kafka/config/kraft/server.properties

    # 7. Generate cluster ID and format
    CLUSTER_ID=\$(/opt/kafka/bin/kafka-storage.sh random-uuid)
    echo "Cluster ID: \$CLUSTER_ID"
    /opt/kafka/bin/kafka-storage.sh format -t "\$CLUSTER_ID" -c /opt/kafka/config/kraft/server.properties || true

    # 8. Create systemd service
    cat > /etc/systemd/system/kafka.service << SYSTEMD_EOF
[Unit]
Description=Apache Kafka (KRaft mode)
After=network.target
StartLimitIntervalSec=0

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

    # 9. Enable and start
    systemctl daemon-reload
    systemctl enable kafka
    systemctl start kafka

    # 10. Wait and verify
    sleep 15
    if systemctl is-active --quiet kafka; then
        echo "=== Kafka is running! ==="
        ss -tlnp | grep 9092 || echo "Port 9092 not yet listening"
    else
        echo "=== Kafka failed to start ==="
        journalctl -u kafka --no-pager -n 30
    fi
else
    echo "Kafka not extracted — skipping Kafka configuration and service setup"
fi

echo "=== User-data completed at \$(date) ==="
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

