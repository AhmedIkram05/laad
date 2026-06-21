# Kafka Module Outputs

output "kafka_private_ip" {
  description = "Private IP address of the Kafka EC2 instance"
  value       = aws_instance.kafka.private_ip
}

output "kafka_public_ip" {
  description = "Public IP address of the Kafka Elastic IP"
  value       = aws_eip.kafka.public_ip
}

output "kafka_eip_id" {
  description = "ID of the Kafka Elastic IP"
  value       = aws_eip.kafka.id
}

output "kafka_instance_id" {
  description = "ID of the Kafka EC2 instance"
  value       = aws_instance.kafka.id
}

output "kafka_sg_id" {
  description = "ID of the Kafka security group (passed through from input)"
  value       = var.kafka_sg_id
}
