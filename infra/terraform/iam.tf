resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "sadhana-backend-runtime"
  display_name = "sadhana-backend-runtime (Cloud Run search API)"
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_es_api_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.es_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# The identity GitHub Actions impersonates via Workload Identity Federation
# (see README's "First-time bootstrap" — the WIF trust binding itself is
# never Terraform-managed, same reasoning as the sibling project: a bad
# apply shouldn't be able to lock CI out of GCP with no CI-driven way back
# in). This one module owns everything (no core/edge split), so its deployer
# needs a broader role set than the sibling project's per-repo deployers.
resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "sadhana-backend-deployer"
  display_name = "sadhana-backend-deployer (GitHub Actions deploy)"
}

resource "google_project_iam_member" "deployer_roles" {
  for_each = toset([
    "roles/run.admin",
    "roles/iam.serviceAccountUser",  # to act-as the runtime SA it also creates
    "roles/iam.serviceAccountAdmin", # to grant secretAccessor on the runtime/es-vm SAs
    "roles/artifactregistry.admin",  # creates the AR repo itself, not just pushes to it
    "roles/compute.admin",           # VPC, subnet, firewall, the ES VM + its disk, the LB
    "roles/secretmanager.admin",     # creates the secret resources + grants accessor
    "roles/resourcemanager.projectIamAdmin",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Needed to run `terraform init`/`apply` at all — the tfstate bucket itself
# isn't Terraform-managed (bootstrap step 1, can't create the bucket that
# stores its own state), so this grants against its name directly.
resource "google_storage_bucket_iam_member" "deployer_tfstate_access" {
  bucket = "${var.project_id}-tfstate"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.deployer.email}"
}
