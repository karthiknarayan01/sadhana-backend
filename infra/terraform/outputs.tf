output "lb_ip" {
  description = "The load balancer's reserved IP — public_url (below) is derived from it, this is mostly useful for confirming DNS/cert provisioning."
  value       = google_compute_global_address.lb_ip.address
}

output "public_url" {
  description = "The real public entry point — https://<public_url>/search?q=... — fronted by Cloud Armor's rate limiter, TLS via a Google-managed cert on a free sslip.io domain. Plain HTTP on this same IP redirects here."
  value       = "https://${local.public_domain}"
}

output "es_internal_ip" {
  description = "The backend VM's private IP (Elasticsearch + search-api both run here) — only reachable from inside the VPC (the LB's NEG, or an IAP SSH tunnel). To debug search-api directly, SSH in (see README) and curl localhost:8080 rather than reaching it over the network — its ingress is LB-only."
  value       = google_compute_instance.elasticsearch.network_interface[0].network_ip
}
