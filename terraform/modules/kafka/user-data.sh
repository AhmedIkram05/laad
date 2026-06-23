#!/bin/bash
# Kafka EC2 user-data script for Amazon Linux 2023
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
set -x

echo "=== Starting Kafka user_data at $(date) ==="

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

KAFKA_VERSION="3.7.0"
KAFKA_TGZ="kafka_2.13-${KAFKA_VERSION}.tgz"
KAFKA_DIR="kafka_2.13-${KAFKA_VERSION}"

# S3 pre-signed URL (refreshed: 2026-06-23, expires 7 days)
S3_URL="https://laad-mlflow-artifacts.s3.eu-west-2.amazonaws.com/kafka/kafka_2.13-3.7.0.tgz?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAZ27UN27KPZUPWSP2%2F20260623%2Feu-west-2%2Fs3%2Faws4_request&X-Amz-Date=20260623T004424Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=67dcebbefe5f5e94f5ce95acee81e0ab03878da69c8107e6101d9f76461ea53d"

download_with() {
    local url="$1"
    local label="$2"
    echo "Downloading Kafka from $label..."
    curl -fsSL --connect-timeout 15 --max-time 180 "$url" -o "/opt/$KAFKA_TGZ" && {
        echo "SUCCESS: Downloaded from $label"
        ls -lh "/opt/$KAFKA_TGZ"
        return 0
    }
    local rc=$?
    echo "FAILED: $label (exit $rc)"
    return $rc
}

# ---------------------------------------------------------------------------
# 1. Install Java (no background contention)
# ---------------------------------------------------------------------------
echo "--- Installing Java ---"
# Wait for any RPM lock then install
for i in $(seq 1 30); do
    if ! lsof /var/lib/rpm/.rpm.lock >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
dnf install -y java-17-amazon-corretto-devel
echo "Java version:"
java -version 2>&1

# ---------------------------------------------------------------------------
# 2. Download Kafka (try S3 pre-signed first, then mirrors)
# ---------------------------------------------------------------------------
echo "--- Downloading Kafka ---"
cd /opt

if [ ! -f "/opt/$KAFKA_TGZ" ]; then
    # Round 1: S3 pre-signed (fastest, same-region)
    download_with "$S3_URL" "S3 pre-signed URL" || \
    # Round 2: Apache mirrors (dlcdn uses Fastly CDN)
    download_with "https://dlcdn.apache.org/kafka/${KAFKA_VERSION}/$KAFKA_TGZ" "dlcdn.apache.org" || \
    download_with "https://downloads.apache.org/kafka/${KAFKA_VERSION}/$KAFKA_TGZ" "downloads.apache.org" || \
    download_with "https://archive.apache.org/dist/kafka/${KAFKA_VERSION}/$KAFKA_TGZ" "archive.apache.org" || \
        echo "WARNING: All downloads failed!"
fi

# ---------------------------------------------------------------------------
# 3. Extract Kafka
# ---------------------------------------------------------------------------
echo "--- Extracting Kafka ---"
if [ -f "/opt/$KAFKA_TGZ" ]; then
    tar -xzf "/opt/$KAFKA_TGZ" -C /opt
    ln -sf "/opt/$KAFKA_DIR" /opt/kafka
    # Fix ownership: chown with -h flag ensures we own the target, not the symlink
    chown -R ec2-user:ec2-user "/opt/$KAFKA_DIR"
    chown -h ec2-user:ec2-user /opt/kafka
    # Pre-create the logs directory so JVM doesn't fail at startup
    mkdir -p "/opt/$KAFKA_DIR/logs"
    chown ec2-user:ec2-user "/opt/$KAFKA_DIR/logs"
    echo "Kafka extracted to /opt/kafka and permissions set"
    ls -la /opt/kafka/
    ls -la /opt/ | grep kafka
else
    echo "ERROR: Kafka tarball not found - cannot proceed"
    echo "=== User-data FAILED at $(date) ==="
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Create Kafka data directory
# ---------------------------------------------------------------------------
mkdir -p /data/kafka
chown -R ec2-user:ec2-user /data/kafka || true

# ---------------------------------------------------------------------------
# 5. Get private IP (IMDSv2)
# ---------------------------------------------------------------------------
echo "--- Determining private IP ---"
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
PRIVATE_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
    http://169.254.169.254/latest/meta-data/local-ipv4)
echo "Private IP: $PRIVATE_IP"

if [ -z "$PRIVATE_IP" ]; then
    echo "ERROR: Could not determine private IP"
    echo "=== User-data FAILED at $(date) ==="
    exit 1
fi

# ---------------------------------------------------------------------------
# 6. Configure KRaft server.properties
# ---------------------------------------------------------------------------
echo "--- Configuring KRaft server.properties ---"
cat > /opt/kafka/config/kraft/server.properties <<-KAFKA_EOF
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@localhost:9093
listeners=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
advertised.listeners=PLAINTEXT://${PRIVATE_IP}:9092
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

grep -E "^(listeners|advertised)" /opt/kafka/config/kraft/server.properties

# ---------------------------------------------------------------------------
# 7. Format storage with KRaft metadata
# ---------------------------------------------------------------------------
echo "--- Formatting KRaft storage ---"
CLUSTER_ID=$(/opt/kafka/bin/kafka-storage.sh random-uuid) || {
    echo "ERROR: Failed to generate cluster UUID"
    exit 1
}
echo "Cluster ID: $CLUSTER_ID"
/opt/kafka/bin/kafka-storage.sh format -t "$CLUSTER_ID" \
    -c /opt/kafka/config/kraft/server.properties

# ---------------------------------------------------------------------------
# 8. Create systemd service
# ---------------------------------------------------------------------------
echo "--- Creating systemd service ---"
cat > /etc/systemd/system/kafka.service <<-SYSTEMD_EOF
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

systemctl daemon-reload
systemctl enable kafka

# ---------------------------------------------------------------------------
# 9. Start Kafka
# ---------------------------------------------------------------------------
echo "--- Verifying permissions before start ---"
ls -la /opt/kafka/logs/ 2>&1 || echo "logs dir not verified"
touch /opt/kafka/logs/.write-test 2>&1 && rm /opt/kafka/logs/.write-test && echo "WRITE TEST PASSED: ec2-user can write to /opt/kafka/logs" || echo "WRITE TEST FAILED"

echo "--- Starting Kafka ---"
systemctl start kafka

# Wait and verify
sleep 20
echo "=== Verification ==="
if systemctl is-active --quiet kafka; then
    echo "*** Kafka is RUNNING ***"
    ss -tlnp | grep 9092 || echo "Port 9092 not yet listening"
else
    echo "*** Kafka failed to start - checking logs ***"
    journalctl -u kafka --no-pager -n 40
    echo "=== FAILURE ==="
    exit 1
fi

echo "=== User-data completed at $(date) ==="
