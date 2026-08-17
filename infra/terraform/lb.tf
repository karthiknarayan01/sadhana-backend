# Cloud Armor only attaches to a proper external HTTP(S) Load Balancer
# backend service (serverless NEG), not a bare Cloud Run URL — so this
# minimal LB exists purely to give the rate limiter something to attach to.
# Plain HTTP + a reserved IP is enough for v1: the API is consumed by the
# app, not browsed, so managed-cert/DNS/custom-domain is deferred until a
# domain is actually wanted (search still travels in the clear until then —
# acceptable for public, non-authenticated shloka lookups, not for anything
# with credentials).
resource "google_compute_global_address" "lb_ip" {
  project = var.project_id
  name    = "sadhana-lb-ip"
}

resource "google_compute_region_network_endpoint_group" "search_api" {
  project               = var.project_id
  name                  = "sadhana-search-api-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_backend_service" "search_api" {
  project               = var.project_id
  name                  = "sadhana-search-api-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.rate_limit.self_link

  backend {
    group = google_compute_region_network_endpoint_group.search_api.id
  }
}

resource "google_compute_url_map" "http" {
  project         = var.project_id
  name            = "sadhana-url-map"
  default_service = google_compute_backend_service.search_api.id
}

resource "google_compute_target_http_proxy" "default" {
  project = var.project_id
  name    = "sadhana-http-proxy"
  url_map = google_compute_url_map.http.id
}

resource "google_compute_global_forwarding_rule" "http" {
  project               = var.project_id
  name                  = "sadhana-http-forwarding-rule"
  target                = google_compute_target_http_proxy.default.id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb_ip.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
