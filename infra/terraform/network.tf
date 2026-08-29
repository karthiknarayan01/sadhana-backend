# A custom VPC exists so the LB's NEG has a network to place the backend VM
# in, and so IAP has a private path to SSH into it — the VM (running both
# Elasticsearch and search-api) has no external IP and is never meant to be
# reachable from the internet except through the LB.
resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = "sadhana-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "subnet" {
  project       = var.project_id
  name          = "sadhana-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.0.0/24"

  # The backend VM reaches Google APIs (Secret Manager, Artifact Registry)
  # via its normal internet egress (see the NAT below), not this setting —
  # kept on regardless since it's free and future resources placed in this
  # subnet may need it.
  private_ip_google_access = true
}

# The ES VM has no external IP by design, but its startup script still needs
# general internet egress (apt package installs, pulling the Elasticsearch
# image from docker.elastic.co) — Private Google Access above only covers
# Google's own APIs, not arbitrary internet hosts. Cloud NAT is what actually
# provides that path while keeping the VM itself unreachable from the
# internet (NAT is outbound-only, never inbound).
resource "google_compute_router" "router" {
  project = var.project_id
  name    = "sadhana-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  project                            = var.project_id
  name                               = "sadhana-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}
