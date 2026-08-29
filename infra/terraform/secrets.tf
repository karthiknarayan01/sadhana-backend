# Metadata only — no google_secret_manager_secret_version here. Real values
# are set once, by hand (see README's "First-time bootstrap"). Never put a
# real secret value in a .tf file or a Terraform-managed secret_version — it
# would sit in plaintext in Terraform state.

# The Elasticsearch bootstrap superuser ("elastic") password — set by hand
# *before* the VM's first boot, since the startup script reads it to launch
# the container. Only the ES VM's own service account can read it.
resource "google_secret_manager_secret" "es_elastic_password" {
  project   = var.project_id
  secret_id = "es-elastic-password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

# An Elasticsearch API key (not the elastic superuser password) scoped to
# read-only search access — minted by hand *after* the VM's first boot, by
# SSHing in via IAP and calling the local ES instance's own API (see
# README). Only the ES VM's own service account can read it (search-api
# runs as a container on that same VM — see elasticsearch.tf).
resource "google_secret_manager_secret" "es_api_key" {
  project   = var.project_id
  secret_id = "es-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}
