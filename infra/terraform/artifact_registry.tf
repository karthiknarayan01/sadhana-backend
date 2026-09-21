resource "google_artifact_registry_repository" "backend_images" {
  project       = var.project_id
  location      = var.region
  repository_id = "sadhana-backend-images"
  format        = "DOCKER"
  description   = "Sadhana search API images, built and pushed by the deploy workflow."

  depends_on = [google_project_service.required]
}
