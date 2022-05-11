variable "name" {
  type    = string
  default = "observe-logs-subscribe"
}

variable "kinesis_firehose" {
  description = "Observe Kinesis Firehose module"
  type = object({
    firehose_delivery_stream = object({ arn = string })
    firehose_iam_policy      = object({ arn = string })
  })
}

variable "log_group_prefixes" {
  description = "All Cloudwatch Log Group matching the listed prefixes will be subscribed"
  type        = list(string)
  default     = []
}

variable "log_group_names" {
  description = "Cloudwatch Log Group names to subscribe to"
  type        = list(string)
  default     = []
}

variable "filter_pattern" {
  description = "The filter pattern to use. For more information, see [Filter and Pattern Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/FilterAndPatternSyntax.html)"
  type        = string
  default     = ""
}

variable "filter_name" {
  description = "Filter name"
  type        = string
  default     = "observe-filter"
}

variable "iam_name_prefix" {
  description = "Prefix used for all created IAM roles and policies"
  type        = string
  default     = "observe-logs-subscribe"
}

variable "iam_role_arn" {
  description = "ARN of IAM role to use for Cloudwatch Logs subscription"
  type        = string
  default     = ""
}

variable "allowed_log_group_prefix" {
  description = "This Lambda created by this template will only look at Log Groups that match this prefix, defaults to all Log Groups"
  type        = string
  default     = ""
}

variable "log_group_expiration_in_days" {
  description = <<EOF
    Expiration to set on the log group for the lambda created by this stack
  EOF
  type        = number
  default     = 365

  validation {
    condition     = contains([1, 3, 7, 14, 30, 90, 365], var.log_group_expiration_in_days)
    error_message = "Expiration not in [1, 3, 7, 14, 30, 90, 365]."
  }
}

variable "lambda_timeout" {
  description = <<EOF
    The amount of time that Lambda allows a function to run before stopping
    it. The maximum allowed value is 900 seconds.
  EOF
  type        = number
  default     = 120
}
