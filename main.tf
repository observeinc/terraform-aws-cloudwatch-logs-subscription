locals {
  partition = data.aws_partition.current.partition
  account   = data.aws_caller_identity.current.account_id
  region    = data.aws_region.current.name

  subscription_filter_role_arn = var.iam_role_arn != "" ? var.iam_role_arn : aws_iam_role.subscription_filter[0].arn

  enabled_lambda_count = length(var.log_group_prefixes) > 0 ? 1 : 0
  log_group_prefix_arns = [for prefix in var.log_group_prefixes :
    "arn:${local.partition}:logs:${local.region}:${local.account}:log-group:${prefix}*"
  ]

  env_vars = {
    "LOG_GROUP_PREFIXES"       = jsonencode(var.log_group_prefixes)
    "LOG_GROUPS_TO_IGNORE"     = jsonencode(var.log_group_names)
    "DESTINATION_ARN"          = var.kinesis_firehose.firehose_delivery_stream.arn
    "DELIVERY_STREAM_ROLE_ARN" = local.subscription_filter_role_arn
    "FILTER_NAME"              = var.filter_name
    "FILTER_PATTERN"           = var.filter_pattern

    # Bump VERSION if we want to re-create the subscription filters even
    # if the user's environment variables haven't changed.
    "VERSION" = 0
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_partition" "current" {}

resource "aws_iam_role" "subscription_filter" {
  count = var.iam_role_arn == "" ? 1 : 0

  name_prefix        = var.iam_name_prefix
  assume_role_policy = <<-EOF
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

resource "aws_iam_role_policy_attachment" "subscription_filter_publish_logs" {
  role       = regex(".*role/(?P<role_name>.*)$", local.subscription_filter_role_arn)["role_name"]
  policy_arn = var.kinesis_firehose.firehose_iam_policy.arn
}

resource "aws_cloudwatch_log_subscription_filter" "explicit_filters" {
  count = length(var.log_group_names)

  name            = var.filter_name
  log_group_name  = var.log_group_names[count.index]
  filter_pattern  = var.filter_pattern
  role_arn        = local.subscription_filter_role_arn
  destination_arn = var.kinesis_firehose.firehose_delivery_stream.arn

  // Explicit filters are created after and deleted before the lambda is triggered
  // to avoid potential state errors.
  depends_on = [aws_cloudformation_stack.lambda_trigger]
}

resource "aws_lambda_permission" "invoke_lambda" {
  count = local.enabled_lambda_count

  function_name = aws_lambda_function.update_log_group_subscriptions[0].function_name
  action        = "lambda:InvokeFunction"
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.new_log_group[0].arn
}

resource "aws_cloudwatch_event_rule" "new_log_group" {
  count = local.enabled_lambda_count

  name_prefix   = var.name
  description   = "Rule to listen for new log groups and trigger the log group subscriber lambda"
  event_pattern = <<-EOF
    {
      "source": ["aws.logs"],
      "detail-type": ["AWS API Call via CloudTrail"],
      "detail": {
        "eventSource": ["logs.amazonaws.com"],
        "eventName": ["CreateLogGroup"]
      }
    }
  EOF
}

resource "aws_cloudwatch_event_target" "new_log_group" {
  count = local.enabled_lambda_count

  target_id = aws_lambda_function.update_log_group_subscriptions[0].id
  rule      = aws_cloudwatch_event_rule.new_log_group[0].name
  arn       = aws_lambda_function.update_log_group_subscriptions[0].arn

  depends_on = [aws_lambda_permission.invoke_lambda]
}

resource "aws_iam_role" "lambda" {
  count = local.enabled_lambda_count

  name_prefix        = var.iam_name_prefix
  description        = "Role for the log group subscriber lambda"
  assume_role_policy = <<-EOF
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Action": "sts:AssumeRole",
          "Principal": {
            "Service": "lambda.amazonaws.com"
          },
          "Effect": "Allow"
        }
      ]
    }
  EOF
}

resource "aws_iam_policy" "subscribe_logs" {
  count = local.enabled_lambda_count

  name_prefix = var.iam_name_prefix
  policy      = <<-EOF
    {
      "Version": "2012-10-17",
      "Statement": [
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
              "logs:DescribeLogGroups"
            ],
            "Resource": [
              "arn:${local.partition}:logs:${local.region}:${local.account}:log-group:*"
            ]
        },
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
              "logs:PutSubscriptionFilter",
              "logs:DescribeSubscriptionFilters",
              "logs:DeleteSubscriptionFilter"
            ],
            "Resource": ${jsonencode(local.log_group_prefix_arns)}
        }
      ]
    }
  EOF
}

resource "aws_iam_role_policy_attachment" "lambda_subscribe_logs" {
  count = length(aws_iam_policy.subscribe_logs) > 0 ? 1 : 0

  role       = aws_iam_role.lambda[0].name
  policy_arn = aws_iam_policy.subscribe_logs[0].arn
}

resource "aws_iam_policy" "pass_role" {
  count = local.enabled_lambda_count

  name_prefix = var.iam_name_prefix
  policy      = <<-EOF
      {
        "Version": "2012-10-17",
        "Statement": [
          {
              "Sid": "",
              "Effect": "Allow",
              "Action": [
                "iam:PassRole"
              ],
              "Resource": [
                  "${local.subscription_filter_role_arn}"
              ]
          }
        ]
      }
  EOF
}

resource "aws_iam_role_policy_attachment" "lambda_pass_role" {
  count = local.enabled_lambda_count

  role       = aws_iam_role.lambda[0].name
  policy_arn = aws_iam_policy.pass_role[0].arn
}

data "aws_iam_policy" "lambda_basic_execution" {
  count = local.enabled_lambda_count

  arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_lambda_basic_execution" {
  count = local.enabled_lambda_count

  role       = aws_iam_role.lambda[0].name
  policy_arn = data.aws_iam_policy.lambda_basic_execution[0].arn
}

data "archive_file" "lambda_code" {
  count = local.enabled_lambda_count

  type        = "zip"
  source_dir  = "${path.module}/lambda/"
  output_path = "${path.module}/files/lambda.zip"
}

resource "aws_lambda_function" "update_log_group_subscriptions" {
  count = local.enabled_lambda_count

  function_name = var.name
  role          = aws_iam_role.lambda[0].arn

  description = <<-EOF
    Look at all specified log groups and add/remove subscriptions filters if necessary
  EOF

  environment {
    variables = local.env_vars
  }

  runtime = "python3.9"
  timeout = var.lambda_timeout
  handler = "index.main"

  filename         = data.archive_file.lambda_code[0].output_path
  source_code_hash = data.archive_file.lambda_code[0].output_base64sha256
}

resource "aws_cloudwatch_log_group" "lambda_log_group" {
  count = local.enabled_lambda_count

  name              = "/aws/lambda/${aws_lambda_function.update_log_group_subscriptions[0].function_name}"
  retention_in_days = var.log_group_expiration_in_days
}

resource "aws_cloudformation_stack" "lambda_trigger" {
  count = local.enabled_lambda_count

  name = "${var.name}-${sha256(jsonencode(local.env_vars))}"

  parameters = {
    "LambdaArn" = aws_lambda_function.update_log_group_subscriptions[0].arn
  }

  template_body = <<-EOF
    AWSTemplateFormatVersion: 2010-09-09
    Parameters:
      LambdaArn:
        Type: "String"
        Default: ""
        Description: "The ARN of the Lambda to trigger"
    Resources:
      InitialLambdaTrigger:
        Type: Custom::InitialLambdaTrigger
        Properties:
          Description: On stack creation, add subscriptions to all existing log groups that match the specified filters. On deletion, remove all subscriptions added by this template.
          ServiceToken: !Ref LambdaArn
  EOF

  depends_on = [aws_iam_policy.subscribe_logs]
}
