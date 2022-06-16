locals {
  partition = data.aws_partition.current.partition
  account   = data.aws_caller_identity.current.account_id
  region    = data.aws_region.current.name

  subscription_filter_role_arn = var.iam_role_arn != "" ? var.iam_role_arn : aws_iam_role.subscription_filter[0].arn

  function_name = var.name
  function_env_vars = {
    "LOG_GROUP_MATCHES"        = join(",", var.log_group_matches)
    "LOG_GROUP_EXCLUDES"       = join(",", var.log_group_excludes)
    "DESTINATION_ARN"          = var.kinesis_firehose.firehose_delivery_stream.arn
    "DELIVERY_STREAM_ROLE_ARN" = local.subscription_filter_role_arn
    "FILTER_NAME"              = var.filter_name
    "FILTER_PATTERN"           = var.filter_pattern

    # Bump VERSION if we want to re-create the subscription filters even
    # if the user's environment variables haven't changed.
    "VERSION" = 1
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

resource "aws_iam_role_policy_attachment" "subscription_filter" {
  role       = regex(".*role/(?P<role_name>.*)$", local.subscription_filter_role_arn)["role_name"]
  policy_arn = var.kinesis_firehose.firehose_iam_policy.arn
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_group_expiration_in_days
}

resource "aws_iam_role" "lambda" {
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

resource "aws_iam_policy" "lambda" {
  name_prefix = var.iam_name_prefix
  policy      = <<-EOF
    {
      "Version": "2012-10-17",
      "Statement": [
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
              "logs:DescribeLogGroups",
              "logs:PutSubscriptionFilter",
              "logs:DescribeSubscriptionFilters",
              "logs:DeleteSubscriptionFilter"
            ],
            "Resource": "arn:${local.partition}:logs:${local.region}:${local.account}:log-group:*"
        },
        {
          "Sid": "",
          "Effect": "Allow",
          "Action": [
            "iam:PassRole"
          ],
          "Resource": "${local.subscription_filter_role_arn}"
        },
        {
          "Sid": "",
          "Effect": "Allow",
          "Action": [
            "events:PutEvents"
          ],
          "Resource": "arn:${local.partition}:events:${local.region}:${local.account}:event-bus/default"
        },
        {
          "Effect": "Allow",
          "Action": [
            "logs:DescribeLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents"
          ],
          "Resource": "${aws_cloudwatch_log_group.lambda.arn}*"
        }
      ]
    }
  EOF
}

resource "aws_iam_role_policy_attachment" "lambda" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda.arn
}

data "archive_file" "lambda_code" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/"
  output_path = "${path.module}/generated/lambda.zip"
}

resource "aws_lambda_function" "lambda" {
  function_name = local.function_name
  role          = aws_iam_role.lambda.arn

  description = <<-EOF
    Look at all specified log groups and add/remove subscriptions filters if necessary
  EOF

  environment {
    variables = local.function_env_vars
  }

  runtime = "python3.9"
  timeout = var.lambda_timeout
  handler = "index.main"

  filename         = data.archive_file.lambda_code.output_path
  source_code_hash = data.archive_file.lambda_code.output_base64sha256

  depends_on = [
    aws_iam_role_policy_attachment.subscription_filter,
    aws_iam_role_policy_attachment.lambda,
    aws_cloudwatch_log_group.lambda,
  ]
}

resource "aws_cloudwatch_event_rule" "new_log_groups" {
  name          = "${var.name}-new-log-groups"
  description   = "Rule to listen for new log groups from aws.logs"
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

resource "aws_cloudwatch_event_rule" "pagination" {
  name           = "${var.name}-pagination"
  description    = "Rule to listen for pagination events from the Lambda function itself"
  event_pattern  = <<-EOF
    {
      "source": ["com.observeinc.autosubscribe"],
      "detail-type": ["pagination"]
    }
  EOF
}

resource "aws_lambda_permission" "event_rules" {
  for_each = {
    new_logs   = aws_cloudwatch_event_rule.new_log_groups
    pagination = aws_cloudwatch_event_rule.pagination
  }

  function_name = aws_lambda_function.lambda.function_name
  action        = "lambda:InvokeFunction"
  principal     = "events.amazonaws.com"
  source_arn    = each.value.arn
}

resource "aws_cloudwatch_event_target" "event_rules" {
  for_each = {
    new_logs   = aws_cloudwatch_event_rule.new_log_groups
    pagination = aws_cloudwatch_event_rule.pagination
  }

  rule           = each.value.name

  arn        = aws_lambda_function.lambda.arn
  depends_on = [aws_lambda_permission.event_rules]
}

resource "aws_cloudformation_stack" "lambda_trigger" {
  name = "${var.name}-${sha256(jsonencode(local.function_env_vars))}"

  parameters = {
    "LambdaArn" = aws_lambda_function.lambda.arn
  }

  timeout_in_minutes = var.lambda_timeout + 1
  template_body      = <<-EOF
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

  depends_on = [aws_cloudwatch_event_target.event_rules]
}
