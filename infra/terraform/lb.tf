# Cloud Armor only attaches to a proper external HTTP(S) Load Balancer
# backend service (serverless NEG), not a bare Cloud Run URL — so this LB
# exists partly to give the rate limiter something to attach to, and partly
# to terminate real TLS: the API is public and unauthenticated, so HTTPS
# isn't optional.
#
# No purchased domain, no Cloud DNS zone: sslip.io is a free wildcard DNS
# service where "<ip-with-dashes>.sslip.io" resolves to that literal IP with
# zero registration and zero propagation delay. Google's managed-cert
# provisioning only checks that the requested domain's DNS resolves to the
# forwarding rule's IP — it doesn't check domain ownership/registration — so
# this satisfies it exactly as well as a real registered domain would, at
# zero cost. The domain is derived from the reserved IP itself, so the whole
# LB (including the cert) comes up in a single `terraform apply`, no
# multi-step "get the IP, then update DNS, then re-apply" dance.
resource "google_compute_global_address" "lb_ip" {
  project = var.project_id
  name    = "sadhana-lb-ip"
}

locals {
  public_domain = "${replace(google_compute_global_address.lb_ip.address, ".", "-")}.sslip.io"
}

# search-api runs as a container on the backend VM (see elasticsearch.tf)
# rather than on Cloud Run, so the LB points at it by IP:port instead of at
# a serverless NEG.
resource "google_compute_network_endpoint_group" "search_api" {
  project      = var.project_id
  name         = "sadhana-search-api-neg"
  zone         = var.zone
  network      = google_compute_network.vpc.id
  subnetwork   = google_compute_subnetwork.subnet.id
  default_port = 8080
}

resource "google_compute_network_endpoint" "search_api" {
  project                = var.project_id
  zone                   = var.zone
  network_endpoint_group = google_compute_network_endpoint_group.search_api.name
  instance               = google_compute_instance.elasticsearch.name
  ip_address             = google_compute_instance.elasticsearch.network_interface[0].network_ip
  port                   = 8080
}

# A serverless NEG got a health check for free from Cloud Run; a standalone
# VM NEG doesn't, so this is new — reuses the API's own /health endpoint.
resource "google_compute_health_check" "search_api" {
  project = var.project_id
  name    = "sadhana-search-api-health-check"

  http_health_check {
    port         = 8080
    request_path = "/health"
  }
}

resource "google_compute_backend_service" "search_api" {
  project               = var.project_id
  name                  = "sadhana-search-api-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.rate_limit.self_link
  health_checks         = [google_compute_health_check.search_api.id]

  backend {
    group                 = google_compute_network_endpoint_group.search_api.id
    balancing_mode        = "RATE"
    max_rate_per_endpoint = 100
  }

  # Every request through the LB (path, status, latency, source IP) lands
  # in Cloud Logging automatically — request-volume/usage visibility with
  # no app code and no data ever collected from the app itself. sample_rate
  # 1.0 logs everything; traffic here is nowhere near the volume where
  # sampling down would matter.
  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_managed_ssl_certificate" "primary" {
  project = var.project_id
  name    = "sadhana-ssl-cert"

  managed {
    domains = [local.public_domain]
  }
}

resource "google_compute_url_map" "https" {
  project         = var.project_id
  name            = "sadhana-url-map"
  default_service = google_compute_backend_service.search_api.id
}

resource "google_compute_target_https_proxy" "default" {
  project          = var.project_id
  name             = "sadhana-https-proxy"
  url_map          = google_compute_url_map.https.id
  ssl_certificates = [google_compute_managed_ssl_certificate.primary.id]
}

resource "google_compute_global_forwarding_rule" "https" {
  project               = var.project_id
  name                  = "sadhana-https-forwarding-rule"
  target                = google_compute_target_https_proxy.default.id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb_ip.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# Plain HTTP on 80 exists only to redirect to HTTPS — no unencrypted serving.
resource "google_compute_url_map" "http_redirect" {
  project = var.project_id
  name    = "sadhana-url-map-http-redirect"

  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  project = var.project_id
  name    = "sadhana-http-proxy"
  url_map = google_compute_url_map.http_redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  project               = var.project_id
  name                  = "sadhana-http-forwarding-rule"
  target                = google_compute_target_http_proxy.redirect.id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb_ip.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
