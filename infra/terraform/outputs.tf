output "lb_ip" {
  description = "Public IP the app should hit — http://<lb_ip>/search?q=... — fronted by Cloud Armor's rate limiter."
  value       = google_compute_global_address.lb_ip.address
}

output "api_url" {
  description = "sadhana-search-api's *.run.app URL. Not the public URL (that's lb_ip, above) — useful for debugging the service directly, though its ingress is LB-only so this alone won't respond from the outside."
  value       = google_cloud_run_v2_service.api.uri
}

output "es_internal_ip" {
  description = "The Elasticsearch VM's private IP — only reachable from inside the VPC (Cloud Run's Direct VPC egress, or an IAP SSH tunnel)."
  value       = google_compute_instance.elasticsearch.network_interface[0].network_ip
}
