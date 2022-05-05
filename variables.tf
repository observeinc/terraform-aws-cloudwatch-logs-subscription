variable "kinesis_firehose" {
  description = "Observe Kinesis Firehose module"
  type = object({
    firehose_delivery_stream = object({ arn = string })
    firehose_iam_policy      = object({ arn = string })
  })
  default = null
}

variable "lambda" {
  description = "Observe Lambda function"
  type = object({
    arn           = string
    function_name = string
  })
  default = null
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
  default     = "observe-kinesis-firehose-"
}

variable "iam_role_arn" {
  description = "ARN of IAM role to use for Cloudwatch Logs subscription"
  type        = string
  default     = ""
}

variable "allow_all_log_groups" {
  description = <<-EOF
    Create a single permission allowing lambda to be triggered by any log group.
    This works around policy limits when subscribing many log groups to a single lambda."
  EOF
  type        = bool
  default     = false
}


variable "statement_id_prefix" {
  description = "Prefix used for Lambda permission statement ID"
  type        = string
  default     = "observe-lambda"
}

variable "stack_name_prefix" {
  description = "Prefix used for Cloudformation Stack Name"
  type        = string
  default     = "observe-autosubscribe"
}
