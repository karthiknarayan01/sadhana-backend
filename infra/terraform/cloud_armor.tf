resource "google_compute_security_policy" "rate_limit" {
  project = var.project_id
  name    = "sadhana-rate-limit"

  rule {
    action   = "throttle"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Per-client-IP rate limit — spec calls for 5-10 req/sec."
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.rate_limit_threshold_per_minute
        interval_sec = 60
      }
    }
  }

  rule {
    action      = "allow"
    priority    = "2147483647"
    description = "Default rule — allow anything not caught above."
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }

  depends_on = [google_project_service.required]
}
