locals {
  subscription_filter_role = var.iam_role_arn != "" ? var.iam_role_arn : aws_iam_role.subscription_filter_role[0].arn

  partition = data.aws_partition.current.partition
  account   = data.aws_caller_identity.current.account_id
  region    = data.aws_region.current.name
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_partition" "current" {}

resource "aws_iam_role" "subscription_filter_role" {
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

resource "aws_iam_role_policy_attachment" "subscription_filter_role_publish_logs" {
  role       = regex(".*role/(?P<role_name>.*)$", local.subscription_filter_role)["role_name"]
  policy_arn = var.kinesis_firehose.firehose_iam_policy.arn
}

resource "aws_cloudwatch_log_subscription_filter" "firehose_delivery_stream" {
  count = length(var.log_group_names)

  name            = var.filter_name
  log_group_name  = var.log_group_names[count.index]
  filter_pattern  = var.filter_pattern
  role_arn        = local.subscription_filter_role
  destination_arn = var.kinesis_firehose.firehose_delivery_stream.arn
}

resource "aws_lambda_permission" "permission_for_events_to_invoke_lambda" {
  function_name = aws_lambda_function.log_group_subscriber_lambda.function_name
  action        = "lambda:InvokeFunction"
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.new_log_group_event_rule.arn
}

resource "aws_lambda_permission" "permission_for_s3_to_invoke_lambda" {
  function_name = aws_lambda_function.log_group_subscriber_lambda.function_name
  action        = "lambda:InvokeFunction"
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.lambda_trigger_bucket.arn
}

resource "aws_cloudwatch_event_rule" "new_log_group_event_rule" {
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

resource "aws_cloudwatch_event_target" "new_log_group_event_rule_target" {
  target_id = aws_lambda_function.log_group_subscriber_lambda.id

  rule = aws_cloudwatch_event_rule.new_log_group_event_rule.name
  arn  = aws_lambda_function.log_group_subscriber_lambda.arn
}

resource "aws_iam_role" "lambda_role" {
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
  name_prefix = var.iam_name_prefix
  policy      = <<-EOF
    {
      "Version": "2012-10-17",
      "Statement": [
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
              "logs:PutSubscriptionFilter",
              "logs:DescribeSubscriptionFilters",
              "logs:DeleteSubscriptionFilter"
            ],
            "Resource": [
                "arn:${local.partition}:logs:${local.region}:${local.account}:log-group:${var.allowed_log_group_prefix}*"
            ]
        }
      ]
    }
  EOF
}

resource "aws_iam_role_policy_attachment" "lambda_role_subscribe_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.subscribe_logs.arn
}

resource "aws_iam_policy" "pass_role" {
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
                  "${local.subscription_filter_role}"
              ]
          }
        ]
      }
  EOF
}

resource "aws_iam_role_policy_attachment" "lambda_role_pass_role" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.pass_role.arn
}

data "aws_iam_policy" "lambda_basic_execution" {
  arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_role_lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = data.aws_iam_policy.lambda_basic_execution.arn
}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/"
  output_path = "${path.module}/files/lambda.zip"
}

resource "aws_lambda_function" "log_group_subscriber_lambda" {
  function_name = var.name
  role          = aws_iam_role.lambda_role.arn

  description = <<-EOF
    Look at all specified log groups and add/remove subscriptions filters if necessary
  EOF

  environment {
    variables = {
      "ALLOWED_LOG_GROUP_PREFIX" = var.allowed_log_group_prefix
      "DESTINATION_ARN"          = var.kinesis_firehose.firehose_delivery_stream.arn
      "DELIVERY_STREAM_ROLE_ARN" = local.subscription_filter_role
      "STACK_NAME"               = var.name
    }
  }

  runtime = "python3.9"
  timeout = var.lambda_timeout
  handler = "index.main"

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
}

resource "aws_cloudwatch_log_group" "lambda_log_group" {
  name              = "/aws/lambda/${aws_lambda_function.log_group_subscriber_lambda.function_name}"
  retention_in_days = var.log_group_expiration_in_days
}

resource "aws_s3_bucket" "lambda_trigger_bucket" {
  bucket_prefix = var.name
}

resource "aws_s3_bucket_notification" "lambda_trigger" {
  bucket = aws_s3_bucket.lambda_trigger_bucket.bucket

  lambda_function {
    events              = ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"]
    lambda_function_arn = aws_lambda_function.log_group_subscriber_lambda.arn
  }

  depends_on = [aws_lambda_permission.permission_for_s3_to_invoke_lambda]
}

// When this is created or destroyed, the lambda should get triggered
resource "aws_s3_bucket_object" "lambda_trigger_object" {
  bucket     = aws_s3_bucket.lambda_trigger_bucket.bucket
  key        = "lambda-trigger"
  content    = ""
  // TODO(luke): can a race condition prevent the notification from making it to the lambda?
  depends_on = [aws_s3_bucket_notification.lambda_trigger, aws_lambda_function.log_group_subscriber_lambda]
}
