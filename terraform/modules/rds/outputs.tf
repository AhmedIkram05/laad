# LAAD RDS Module Outputs

output "rds_endpoint" {
  description = "Endpoint of the RDS instance"
  value       = aws_db_instance.main.endpoint
}

output "rds_port" {
  description = "Port of the RDS instance"
  value       = aws_db_instance.main.port
}

output "rds_db_name" {
  description = "Database name of the RDS instance"
  value       = aws_db_instance.main.db_name
}

output "db_master_secret_arn" {
  description = "ARN of the DB master secret in Secrets Manager"
  value       = data.aws_secretsmanager_secret.db_master.arn
}

output "rds_instance_id" {
  description = "ID of the RDS instance"
  value       = aws_db_instance.main.id
}
