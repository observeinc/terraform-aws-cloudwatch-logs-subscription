terraform {
  required_version = ">= 1.1"

  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.2"
    }
    aws = {
      source  = "hashicorp/aws"
      version = ">= 2.68"
    }
  }
}
