locals {
  iam_role_arn = var.kinesis_firehose != null ? (var.iam_role_arn != "" ? var.iam_role_arn : aws_iam_role.this[0].arn) : null

  account = data.aws_caller_identity.current.account_id
  region  = data.aws_region.current.name
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}


resource "aws_iam_role" "this" {
  count = var.kinesis_firehose != null && var.iam_role_arn == "" ? 1 : 0

  name_prefix        = var.iam_name_prefix
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "logs.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "firehose_delivery_stream" {
  count = var.kinesis_firehose != null ? 1 : 0

  role       = regex(".*role/(?P<role_name>.*)$", local.iam_role_arn)["role_name"]
  policy_arn = var.kinesis_firehose != null ? var.kinesis_firehose.firehose_iam_policy.arn : ""
}

resource "aws_cloudwatch_log_subscription_filter" "firehose_delivery_stream" {
  count = var.kinesis_firehose != null ? length(var.log_group_names) : 0

  name            = var.filter_name
  log_group_name  = var.log_group_names[count.index]
  filter_pattern  = var.filter_pattern
  role_arn        = local.iam_role_arn
  destination_arn = var.kinesis_firehose.firehose_delivery_stream.arn
}

resource "aws_lambda_permission" "permission" {
  count = var.lambda != null && !var.allow_all_log_groups ? length(var.log_group_names) : 0

  action              = "lambda:InvokeFunction"
  function_name       = var.lambda.function_name
  principal           = format("logs.%s.amazonaws.com", local.region)
  source_arn          = format("arn:aws:logs:%s:%s:log-group:%s:*", local.region, local.account, var.log_group_names[count.index])
  statement_id_prefix = var.statement_id_prefix
}

resource "aws_lambda_permission" "permission_allow_all" {
  count = var.lambda != null && var.allow_all_log_groups ? 1 : 0

  action              = "lambda:InvokeFunction"
  function_name       = var.lambda.function_name
  principal           = format("logs.%s.amazonaws.com", local.region)
  source_arn          = format("arn:aws:logs:%s:%s:log-group:*:*", local.region, local.account)
  statement_id_prefix = var.statement_id_prefix
}

resource "aws_cloudwatch_log_subscription_filter" "lambda" {
  count = var.lambda != null ? length(var.log_group_names) : 0

  name            = var.filter_name
  log_group_name  = var.log_group_names[count.index]
  filter_pattern  = var.filter_pattern
  destination_arn = var.lambda.arn

  depends_on = [aws_lambda_permission.permission, aws_lambda_permission.permission_allow_all]
}

