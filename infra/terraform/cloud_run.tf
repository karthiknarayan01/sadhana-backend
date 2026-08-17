resource "google_cloud_run_v2_service" "api" {
  project             = var.project_id
  name                = "sadhana-search-api"
  location            = var.region
  deletion_protection = false # cheap/instant to recreate on every deploy

  # LB-only — omitting this means Cloud Armor is trivially bypassed by
  # hitting this service's own *.run.app URL directly.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.runtime.email

    # Direct VPC egress (GA) — not a google_vpc_access_connector, which has
    # an always-on ~$9/mo minimum. PRIVATE_RANGES_ONLY since the only thing
    # this service needs the VPC for is reaching the private ES VM; anything
    # else (there is nothing else today) keeps using the default path.
    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.subnet.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend_images.repository_id}/search-api:${var.image_tag}"

      env {
        name  = "ES_HOST"
        value = "http://${google_compute_instance.elasticsearch.network_interface[0].network_ip}:9200"
      }

      env {
        name  = "ES_INDEX"
        value = "shlokas"
      }

      env {
        name = "ES_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.es_api_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}
