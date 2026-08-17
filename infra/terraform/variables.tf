variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east1"
}

variable "zone" {
  description = "Zone for the Elasticsearch VM and its data disk — must be in `region`."
  type        = string
  default     = "us-east1-b"
}

variable "image_tag" {
  description = "Docker tag in Artifact Registry to deploy — the deploy workflow passes the git SHA."
  type        = string
}

variable "es_machine_type" {
  description = "Single-node Elasticsearch VM size. e2-small (2GB RAM) is enough for a v1 catalog of a few hundred shlokas; bump to e2-medium if the JVM heap starts swapping."
  type        = string
  default     = "e2-small"
}

variable "es_data_disk_size_gb" {
  type    = number
  default = 20
}

variable "rate_limit_threshold_per_minute" {
  description = "Cloud Armor per-client-IP throttle. Spec calls for 5-10 req/sec; Cloud Armor's rate_limit_threshold is per-minute, so this is that range * 60."
  type        = number
  default     = 300
}
