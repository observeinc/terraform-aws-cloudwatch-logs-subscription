# IMPORTANT: Also update README.md if updating the variables here.

variable "name" {
  type        = string
  default     = "observe-logs-subscription"
  nullable    = false
  description = "Module name. Used to determine the name of some resources"
}

variable "kinesis_firehose" {
  description = "Observe Kinesis Firehose module"
  type = object({
    firehose_delivery_stream = object({ arn = string })
    firehose_iam_policy      = object({ arn = string })
  })
}

variable "log_group_matches" {
  description = <<-EOF
    A list of regex patterns. If a Log Group fully matches any regex pattern in the list,
    it will be subscribed to. By "fully matches", we mean that the
    entire log group name must match a pattern.
  EOF
  type        = list(string)
  default     = [".*"]

  validation {
    condition     = can([for x in var.log_group_matches : regexall(x, "")])
    error_message = "Variable log_group_matches contains invalid regex."
  }
}

variable "log_group_excludes" {
  description = <<-EOF
    A list of regex patterns. If a Log Group fully matches any regex pattern in the list, it will
    not be subscribed to. log_group_excludes takes precedence over log_group_matches.
  EOF

  type    = list(string)
  default = []

  validation {
    condition     = can([for x in var.log_group_excludes : regexall(x, "")])
    error_message = "Variable log_group_excludes contains invalid regex."
  }
}

variable "filter_pattern" {
  description = <<-EOF
    The filter pattern that selects the log events that will be sent to Observe for each CloudWatch Logs group. To send all events, leave this empty (""). For more information, see [Filter and Pattern Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/FilterAndPatternSyntax.html).
  EOF
  type        = string
  default     = ""
}

variable "filter_name" {
  description = "Name of all created Log Group Subscription Filters"
  type        = string
  default     = "observe-logs-subscription"
}

variable "iam_name_prefix" {
  description = "Prefix used for all created IAM roles and policies"
  type        = string
  default     = "observe-logs-subscription"
  nullable    = false
}

variable "iam_role_arn" {
  description = <<-EOF
    ARN of IAM role to use for Cloudwatch Logs subscription.
    If this is not specified, then an IAM role is created.
  EOF
  type        = string
  default     = ""
}

variable "log_group_expiration_in_days" {
  description = <<-EOF
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
  description = <<-EOF
    The amount of time that Lambda allows a function to run before stopping
    it. The maximum allowed value is 900 seconds.
  EOF
  type        = number
  default     = 300
}

variable "lambda_memory" {
  description = <<-EOF
    The amount of memory available to the Lambda function, in megabytes.
    See https://docs.aws.amazon.com/lambda/latest/operatorguide/computing-power.html for more info.
  EOF
  type        = number
  default     = 128
}

variable "ignore_delete_errors" {
  description = <<-EOF
    If an error occurs while deleting subscription filters, ignore it, leaving behind any remaining filters.
  EOF
  type        = bool
  default     = false
}

variable "tags" {
  description = "A map of tags to add to all resources"
  type        = map(string)
  default     = {}
}
