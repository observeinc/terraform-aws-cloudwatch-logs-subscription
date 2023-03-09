# AWS CloudWatch Log Subscriptions Terraform module

Terraform module that sets up CloudWatch Log Group Subscription Filters. This makes it easier to forward log data to Observe, through the Observe Kinesis Firehose module.

By default, the module will create subscription filters for all log groups.

## Usage

```hcl
resource "aws_cloudwatch_log_group" "group" {
  name_prefix = random_pet.run.id
}

module "observe_kinesis_firehose" {
  source           = "github.com/observeinc/terraform-aws-kinesis-firehose"
  observe_customer = var.observe_customer
  observe_token    = var.observe_token
  name             = random_pet.run.id
}

module "observe_kinesis_firehose_cloudwatch_logs_subscription" {
  source           = "https://github.com/observeinc/terraform-aws-cloudwatch-logs-subscription"
  kinesis_firehose = module.observe_kinesis_firehose

  # Collect the log group defined above, all Elastic Beanstalk logs,
  # and API Gateway execution logs
  log_group_matches  = [
    aws_cloudwatch_log_group.group.name,
    "/aws/elasticbeanstalk/.*",
    "API-Gateway-Execution-Logs.*",
  ]
  
  # Don't collect any Elastic Beanstalk Nginx access logs
  log_group_excludes = ["/aws/elasticbeanstalk/.*/var/log/nginx/access.log"]
}
```

This module will create multiple CloudWatch subscription filters. 
If no role ARN is provided, a new role will be created.


<!-- BEGINNING OF PRE-COMMIT-TERRAFORM DOCS HOOK -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.1 |
| <a name="requirement_archive"></a> [archive](#requirement\_archive) | >= 2.2 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 2.68 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_archive"></a> [archive](#provider\_archive) | >= 2.2 |
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 2.68 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [aws_cloudformation_stack.lambda_trigger](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudformation_stack) | resource |
| [aws_cloudwatch_event_rule.new_log_groups](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_rule) | resource |
| [aws_cloudwatch_event_rule.pagination](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_rule) | resource |
| [aws_cloudwatch_event_target.event_rules](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_event_target) | resource |
| [aws_cloudwatch_log_group.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_iam_policy.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_policy) | resource |
| [aws_iam_role.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.subscription_filter](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy_attachment.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_iam_role_policy_attachment.subscription_filter](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_lambda_function.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) | resource |
| [aws_lambda_permission.event_rules](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [archive_file.lambda_code](https://registry.terraform.io/providers/hashicorp/archive/latest/docs/data-sources/file) | data source |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_partition.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/partition) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_filter_name"></a> [filter\_name](#input\_filter\_name) | Name of all created Log Group Subscription Filters | `string` | `"observe-logs-subscription"` | no |
| <a name="input_filter_pattern"></a> [filter\_pattern](#input\_filter\_pattern) | The filter pattern to use. For more information, see [Filter and Pattern Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/FilterAndPatternSyntax.html)" | `string` | `""` | no |
| <a name="input_iam_name_prefix"></a> [iam\_name\_prefix](#input\_iam\_name\_prefix) | Prefix used for all created IAM roles and policies | `string` | `"observe-logs-subscription"` | no |
| <a name="input_iam_role_arn"></a> [iam\_role\_arn](#input\_iam\_role\_arn) | ARN of IAM role to use for Cloudwatch Logs subscription.<br>If this is not specified, then an IAM role is created. | `string` | `""` | no |
| <a name="input_ignore_delete_errors"></a> [ignore\_delete\_errors](#input\_ignore\_delete\_errors) | Ignore CloudFormation stack errors from deletion events.<br><br>Setting this to true means that leftover Subscription Filters could remain. | `bool` | `false` | no |
| <a name="input_kinesis_firehose"></a> [kinesis\_firehose](#input\_kinesis\_firehose) | Observe Kinesis Firehose module | <pre>object({<br>    firehose_delivery_stream = object({ arn = string })<br>    firehose_iam_policy      = object({ arn = string })<br>  })</pre> | n/a | yes |
| <a name="input_lambda_memory"></a> [lambda\_memory](#input\_lambda\_memory) | The amount of memory available to the Lambda function, in megabytes.<br>See https://docs.aws.amazon.com/lambda/latest/operatorguide/computing-power.html for more info. | `number` | `128` | no |
| <a name="input_lambda_timeout"></a> [lambda\_timeout](#input\_lambda\_timeout) | The amount of time that Lambda allows a function to run before stopping<br>it. The maximum allowed value is 900 seconds. | `number` | `300` | no |
| <a name="input_log_group_excludes"></a> [log\_group\_excludes](#input\_log\_group\_excludes) | A list of regex patterns. If a Log Group fully matches any regex pattern in the list, it will<br>not be subscribed to. log\_group\_excludes takes precedence over log\_group\_matches. | `list(string)` | `[]` | no |
| <a name="input_log_group_expiration_in_days"></a> [log\_group\_expiration\_in\_days](#input\_log\_group\_expiration\_in\_days) | Expiration to set on the log group for the lambda created by this stack | `number` | `365` | no |
| <a name="input_log_group_matches"></a> [log\_group\_matches](#input\_log\_group\_matches) | A list of regex patterns. If a Log Group fully matches any regex pattern in the list,<br>it will be subscribed to. By "fully matches", we mean that the<br>entire log group name must match a pattern. | `list(string)` | <pre>[<br>  ".*"<br>]</pre> | no |
| <a name="input_name"></a> [name](#input\_name) | Module name. Used to determine the name of some resources | `string` | `"observe-logs-subscription"` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | A map of tags to add to all resources | `map(string)` | `{}` | no |

## Outputs

No outputs.
<!-- END OF PRE-COMMIT-TERRAFORM DOCS HOOK -->

## License

Apache 2 Licensed. See LICENSE for full details.