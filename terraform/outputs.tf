output "public_ip" {
  description = "IP elastica de la instancia"
  value       = aws_eip.deploy_tracker.public_ip
}

output "instance_id" {
  description = "ID de la instancia"
  value       = aws_instance.deploy_tracker.id
}

output "api_url" {
  description = "URL base de la API"
  value       = "http://${aws_eip.deploy_tracker.public_ip}:8000"
}
