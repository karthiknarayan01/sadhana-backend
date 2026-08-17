resource "google_compute_disk" "es_data" {
  project = var.project_id
  name    = "sadhana-es-data"
  zone    = var.zone
  type    = "pd-balanced"
  size    = var.es_data_disk_size_gb
}

resource "google_service_account" "es_vm" {
  project      = var.project_id
  account_id   = "sadhana-es-vm"
  display_name = "sadhana-es-vm (Elasticsearch host)"
}

# Only the bootstrap password — the API key the Cloud Run runtime service
# uses (es-api-key, see iam.tf) is minted by hand, once, after the VM's
# first boot, and this VM's own service account never gets access to it.
resource "google_secret_manager_secret_iam_member" "es_vm_reads_bootstrap_password" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.es_elastic_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.es_vm.email}"
}

resource "google_compute_instance" "elasticsearch" {
  project      = var.project_id
  name         = "sadhana-elasticsearch"
  zone         = var.zone
  machine_type = var.es_machine_type
  tags         = ["elasticsearch"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
    }
  }

  attached_disk {
    source      = google_compute_disk.es_data.id
    device_name = "es-data"
  }

  network_interface {
    network    = google_compute_network.vpc.id
    subnetwork = google_compute_subnetwork.subnet.id
    # No access_config block — deliberately no external IP. This is what
    # makes the VM unreachable from the public internet at all, firewall
    # rules aside.
  }

  service_account {
    email  = google_service_account.es_vm.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = file("${path.module}/scripts/es-startup.sh")
  }

  depends_on = [google_project_service.required]
}
