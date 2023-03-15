provider "aws" {
  region  = "us-west-2"
  profile = "thunderdome"
}

resource "random_id" "this" {
  byte_length = 8
}

resource "aws_cloudwatch_log_group" "group" {
  name = "test-subscription-${random_id.this.hex}"
}

module "cloudwatch_kinesis_firehose_tf" {
  source           = "github.com/observeinc/terraform-aws-kinesis-firehose" # tflint-ignore: terraform_module_pinned_source
  name             = "test-subscription-tf-${random_id.this.hex}"
  observe_customer = "101"
  observe_token    = "fake:token"
}

module "cloudwatch_logs_subscription" {
  source           = "../"
  name             = "test-subscription-tf-${random_id.this.hex}"
  filter_name      = "test-tf-${random_id.this.hex}"
  kinesis_firehose = module.cloudwatch_kinesis_firehose_tf
}

resource "aws_iam_role" "subscription_filter" {
  name               = "test-subscription-${random_id.this.hex}"
  assume_role_policy = data.aws_iam_policy_document.subscription_filter.json
}

data "aws_iam_policy_document" "subscription_filter" {
  statement {
    actions = [
      "sts:AssumeRole"
    ]
    principals {
      type        = "Service"
      identifiers = ["logs.amazonaws.com"]
    }
    effect = "Allow"
    sid    = ""
  }
}

module "cloudwatch_kinesis_firehose_cfn" {
  source           = "github.com/observeinc/terraform-aws-kinesis-firehose" # tflint-ignore: terraform_module_pinned_source
  name             = "test-subscription-cfn-${random_id.this.hex}"
  observe_customer = "101"
  observe_token    = "fake:token"
}

resource "aws_iam_role_policy_attachment" "subscription_filter" {
  role       = aws_iam_role.subscription_filter.name
  policy_arn = module.cloudwatch_kinesis_firehose_cfn.firehose_iam_policy.arn
}

resource "aws_cloudformation_stack" "this" {
  name = "test-subscription-cfn-${random_id.this.hex}"

  template_body = file("../cloudformation/generated/subscribelogs.yaml")

  capabilities = ["CAPABILITY_IAM"]

  parameters = {
    "CollectionStackName"           = "test-subscription-cfn"
    "LogGroupMatches"               = ".*"
    "FilterName"                    = "test-cfn-${random_id.this.hex}"
    "LogGroupExpirationInDays"      = 7
    "LambdaTimeout"                 = 30
    "DestinationArnOverride"        = module.cloudwatch_kinesis_firehose_cfn.firehose_delivery_stream.arn
    "DeliveryStreamRoleArnOverride" = aws_iam_role.subscription_filter.arn
  }
  disable_rollback = true
}
