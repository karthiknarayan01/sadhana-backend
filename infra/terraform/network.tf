# A custom VPC exists for exactly one reason: giving the Cloud Run API
# service a private path (Direct VPC egress — GA, not a
# google_vpc_access_connector, which has an always-on ~$9/mo minimum for no
# benefit at this scale) to the Elasticsearch VM, which has no external IP
# and is never meant to be reachable from the internet.
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

  # Cloud Run's Direct VPC egress needs Private Google Access to reach
  # Google APIs (e.g. Secret Manager, for the runtime service account) from
  # inside the VPC.
  private_ip_google_access = true
}
