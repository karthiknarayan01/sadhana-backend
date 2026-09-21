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

resource "google_secret_manager_secret_iam_member" "es_vm_reads_bootstrap_password" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.es_elastic_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.es_vm.email}"
}

# search-api runs as a container on this same VM (see the instance's
# metadata below and infra/terraform/scripts/redeploy-api.sh) rather than on
# Cloud Run, so it's this SA — not a separate Cloud Run runtime SA — that
# now needs to read the API's ES credential and pull its image.
resource "google_secret_manager_secret_iam_member" "es_vm_reads_api_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.es_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.es_vm.email}"
}

# es-startup.sh mints es-api-key itself on first boot rather than requiring
# a human to SSH in and do it by hand — secretVersionAdder (not the broader
# secretmanager.admin) is the least-privilege role that lets it write that
# one version without also being able to read/manage the secret resource
# itself or touch es-elastic-password.
resource "google_secret_manager_secret_iam_member" "es_vm_writes_api_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.es_api_key.secret_id
  role      = "roles/secretmanager.secretVersionAdder"
  member    = "serviceAccount:${google_service_account.es_vm.email}"
}

resource "google_project_iam_member" "es_vm_reads_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.es_vm.email}"
}

# Runs both Elasticsearch and search-api (talking to each other over
# localhost) — resource/instance names and the "elasticsearch" tag predate
# that and are left as-is to avoid an unnecessary VM recreation; read them
# as "the backend VM", not literally ES-only.
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
    # Read by infra/terraform/scripts/redeploy-api.sh, which the deploy
    # workflow SSHes in to run on every push to dev — kept as metadata
    # (rather than baked into the script itself) so the same script works
    # unmodified regardless of which project/region it's run against.
    region = var.region
    # OS Login (rather than metadata-based SSH keys) is what lets the
    # deployer SA's `gcloud compute ssh`/`scp` calls authenticate without
    # any manually managed key material — see the iap.tunnelResourceAccessor
    # + osAdminLogin grants in iam.tf.
    enable-oslogin = "TRUE"
  }

  depends_on = [google_project_service.required]
}
