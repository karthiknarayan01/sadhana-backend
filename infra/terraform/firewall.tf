# search-api and Elasticsearch now run on the same VM and talk over
# localhost (see elasticsearch.tf), so nothing external needs to reach port
# 9200 at all anymore — this rule, not a rule on 9200, is what actually
# keeps Elasticsearch off the internet. Only the LB's own proxy/health-check
# ranges (not the whole internet) can reach the API port; everything else is
# implicitly denied by VPC default-deny.
resource "google_compute_firewall" "allow_lb_to_api" {
  project = var.project_id
  name    = "sadhana-allow-lb-to-api"
  network = google_compute_network.vpc.id

  direction     = "INGRESS"
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"] # Google LB + health-check ranges
  target_tags   = ["elasticsearch"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
}

# The ES VM has no external IP, so there's no way to SSH into it directly —
# IAP TCP forwarding tunnels through Google's own infra instead
# (`gcloud compute ssh --tunnel-through-iap`), needed for the one-time manual
# step of minting the Elasticsearch API key (see infra README).
resource "google_compute_firewall" "allow_iap_ssh" {
  project = var.project_id
  name    = "sadhana-allow-iap-ssh"
  network = google_compute_network.vpc.id

  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"] # Google's fixed IAP TCP forwarding range
  target_tags   = ["elasticsearch"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
