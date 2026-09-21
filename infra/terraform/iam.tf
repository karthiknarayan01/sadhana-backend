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
    "roles/iam.serviceAccountUser",  # to act-as the es-vm SA it also creates
    "roles/iam.serviceAccountAdmin", # to grant secretAccessor on the es-vm SA
    "roles/artifactregistry.admin",  # creates the AR repo itself, not just pushes to it
    "roles/compute.admin",           # VPC, subnet, firewall, the backend VM + its disk, the LB
    "roles/secretmanager.admin",     # creates the secret resources + grants accessor
    "roles/resourcemanager.projectIamAdmin",
    # search-api now redeploys over SSH to the backend VM instead of via
    # `gcloud run deploy`/Terraform's Cloud Run image reference — these two
    # are what let the deploy job's `gcloud compute ssh`/`scp` calls
    # authenticate via OS Login with no manually managed key material, and
    # actually reach the VM (which has no external IP) through IAP.
    "roles/iap.tunnelResourceAccessor",
    "roles/compute.osAdminLogin",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Needed to run `terraform init`/`apply` at all — the tfstate bucket itself
# isn't Terraform-managed (bootstrap step 1, can't create the bucket that
# stores its own state), so this grants against its name directly.
#
# storage.admin, not objectAdmin: this resource is self-referential — every
# `terraform apply` the deployer SA runs re-reads this very IAM binding to
# compute its diff, which needs bucket-level storage.buckets.getIamPolicy.
# objectAdmin only grants object-level permissions, not that, which fails
# every apply after the first (the first succeeds by luck, applied with a
# human's broader local credentials during bootstrap).
resource "google_storage_bucket_iam_member" "deployer_tfstate_access" {
  bucket = "${var.project_id}-tfstate"
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.deployer.email}"
}
