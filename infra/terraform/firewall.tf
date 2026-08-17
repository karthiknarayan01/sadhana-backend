# The resource that actually enforces "Elasticsearch never touches the
# internet": the ES VM has no external IP (see elasticsearch.tf) and this is
# the *only* ingress rule targeting it — traffic from the subnet Cloud Run's
# Direct VPC egress uses, on the ES port, nothing else. Everything else is
# implicitly denied by VPC default-deny.
resource "google_compute_firewall" "allow_cloud_run_to_es" {
  project = var.project_id
  name    = "sadhana-allow-cloud-run-to-es"
  network = google_compute_network.vpc.id

  direction     = "INGRESS"
  source_ranges = [google_compute_subnetwork.subnet.ip_cidr_range]
  target_tags   = ["elasticsearch"]

  allow {
    protocol = "tcp"
    ports    = ["9200"]
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
