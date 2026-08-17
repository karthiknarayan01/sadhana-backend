output "lb_ip" {
  description = "The load balancer's reserved IP — public_url (below) is derived from it, this is mostly useful for confirming DNS/cert provisioning."
  value       = google_compute_global_address.lb_ip.address
}

output "public_url" {
  description = "The real public entry point — https://<public_url>/search?q=... — fronted by Cloud Armor's rate limiter, TLS via a Google-managed cert on a free sslip.io domain. Plain HTTP on this same IP redirects here."
  value       = "https://${local.public_domain}"
}

output "api_url" {
  description = "sadhana-search-api's *.run.app URL. Not the public URL (that's lb_ip, above) — useful for debugging the service directly, though its ingress is LB-only so this alone won't respond from the outside."
  value       = google_cloud_run_v2_service.api.uri
}

output "es_internal_ip" {
  description = "The Elasticsearch VM's private IP — only reachable from inside the VPC (Cloud Run's Direct VPC egress, or an IAP SSH tunnel)."
  value       = google_compute_instance.elasticsearch.network_interface[0].network_ip
}
