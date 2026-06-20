# LAAD VPC Module Outputs

output "vpc_id" {
  description = "ID of the LAAD VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (one per AZ)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets (one per AZ)"
  value       = aws_subnet.private[*].id
}

output "alb_sg_id" {
  description = "ID of the ALB security group"
  value       = aws_security_group.alb_sg.id
}

output "ecs_api_sg_id" {
  description = "ID of the ECS API security group"
  value       = aws_security_group.ecs_api_sg.id
}

output "ecs_consumer_sg_id" {
  description = "ID of the ECS consumer security group"
  value       = aws_security_group.ecs_consumer_sg.id
}

output "ecs_generator_sg_id" {
  description = "ID of the ECS generator security group"
  value       = aws_security_group.ecs_generator_sg.id
}

output "rds_sg_id" {
  description = "ID of the RDS security group"
  value       = aws_security_group.rds_sg.id
}

output "kafka_sg_id" {
  description = "ID of the Kafka security group"
  value       = aws_security_group.kafka_sg.id
}

output "redis_sg_id" {
  description = "ID of the Redis security group"
  value       = aws_security_group.redis_sg.id
}

output "chromadb_sg_id" {
  description = "ID of the ChromaDB security group"
  value       = aws_security_group.chromadb_sg.id
}

output "nat_gateway_id" {
  description = "ID of the NAT Gateway"
  value       = aws_nat_gateway.main.id
}

output "nat_gateway_public_ip" {
  description = "Public IP address of the NAT Gateway"
  value       = aws_eip.nat.public_ip
}
