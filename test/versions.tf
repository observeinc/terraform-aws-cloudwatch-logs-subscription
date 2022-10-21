terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 3.4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.4.3"
    }
  }
  required_version = ">= 0.13"
}
