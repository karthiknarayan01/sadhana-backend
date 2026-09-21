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

variable "es_machine_type" {
  description = "Backend VM size — runs both Elasticsearch and search-api. e2-small (2GB RAM) is enough for a v1 catalog of a few hundred shlokas; bump to e2-medium if the JVM heap starts swapping or search-api's own memory use makes that worse."
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
