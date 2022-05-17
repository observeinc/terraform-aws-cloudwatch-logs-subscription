import dataclasses
import logging
import os
import re

import boto3

import cfnresponse

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@dataclasses.dataclass
class SubscriptionArgs:
    destination_arn: str
    filter_name: str
    filter_pattern: str
    role_arn: str


def modify_subscription(client, is_create: bool, log_group_name: str, subscription_args: SubscriptionArgs):
    logger.info('modify_subscription: %s %s %s',
                is_create, log_group_name, subscription_args)

    found_filters = client.describe_subscription_filters(
        logGroupName=log_group_name)
    logger.info('log group %s has filters %s', log_group_name, found_filters)

    filter_exists = False
    for f in found_filters['subscriptionFilters']:
        if is_create and f['destinationArn'] == subscription_args.destination_arn:
            return True  # A subscription to this destination ARN already exists
        if f['filterName'] == subscription_args.filter_name:
            filter_exists = True

    if is_create and (not filter_exists):
        try:
            client.put_subscription_filter(logGroupName=log_group_name,
                                           destinationArn=subscription_args.destination_arn,
                                           filterName=subscription_args.filter_name,
                                           filterPattern=subscription_args.filter_pattern,
                                           roleArn=subscription_args.role_arn)
            logger.info('created subscription filter %s for log group %s',
                        subscription_args.filter_name, log_group_name)
        except Exception as err:
            logger.error(
                'error adding subscription to log group %s: %s', log_group_name, err)
            return False

    if (not is_create) and filter_exists:
        try:
            client.delete_subscription_filter(logGroupName=log_group_name,
                                              filterName=subscription_args.filter_name)
            logger.info('deleted subscription filter %s for log group %s',
                        subscription_args.filter_name, log_group_name)
        except Exception as err:
            logger.error(
                'error removing subscription from log group %s: %s', log_group_name, err)
            return False
    return True


def modify_subscriptions(client, is_create: str, matches: list, exclusions: list, subscription_args: SubscriptionArgs):
    logger.info('modify_subscriptions: %s %s %s %s',
                is_create, matches, exclusions, subscription_args)

    successes, total = 0, 0
    paginator = client.get_paginator('describe_log_groups')
    for page in paginator.paginate():
        for lg in page['logGroups']:
            name = lg['logGroupName']
            exclude = any([re.search(pattern, name)
                           for pattern in exclusions])
            if exclude:
                logging.info(
                    'log group %s matches an exclusion regex pattern %s', name, exclusions)
            else:
                match = any([re.search(pattern, name)
                            for pattern in matches])
                if match:
                    success = modify_subscription(
                        client, is_create, name, subscription_args)
                    successes, total = successes + \
                        (1 if success else 0), total+1
                else:
                    logging.info(
                        'no matches for log group %s in %s', name, matches)

    logger.info('succeeeded updating (%d/%d) log groups matching prefixes %s',
                successes, total, matches)
    return successes > 0 or total == 0


def main(event, context):
    matchStr = os.environ['LOG_GROUP_MATCHES']
    exclusionStr = os.environ['LOG_GROUP_EXCLUDES']
    filter_name = os.environ['FILTER_NAME']
    filter_pattern = os.environ['FILTER_PATTERN']
    destination_rn = os.environ['DESTINATION_ARN']
    delivery_role = os.environ['DELIVERY_STREAM_ROLE_ARN']

    matches = matchStr.split(',') if matchStr != "" else []
    exclusions = exclusionStr.split(',') if exclusionStr != "" else []
    args = SubscriptionArgs(destination_rn, filter_name,
                            filter_pattern, delivery_role)

    logger.info('received event: %s', event)

    client = boto3.client('logs')

    is_cfn_event = 'ResponseURL' in event
    is_eventbridge_event = 'detail' in event
    if is_cfn_event:
        try:
            logger.info(
                'assuming event is a CloudFormation create or delete event')
            any_successes = False
            if event['RequestType'] == 'Create':
                any_successes = modify_subscriptions(
                    client, True, matches, exclusions, args)
            elif event['RequestType'] == 'Delete':
                any_successes = modify_subscriptions(
                    client, False, matches, exclusions, args)

            if any_successes:
                cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            else:
                cfnresponse.send(event, context, cfnresponse.FAILED, {
                                 'Data': 'Error: unable to create subscriptions for any log groups'})
        except Exception as e:
            logger.error('unexpected exception: %s', e)
            cfnresponse.send(event, context, cfnresponse.FAILED, {
                'Data': str(e)})
    elif is_eventbridge_event:
        logger.info('assuming event is an EventBridge event')
        name = event['detail']['requestParameters']['logGroupName']

        exclude = any([re.search(pattern, name) for pattern in exclusions])
        if exclude:
            logging.info(
                'log group %s matches an exclusion regex pattern %s', name, exclusions)
        else:
            match = any([re.search(pattern, name) for pattern in matches])
            if match:
                _ = modify_subscription(client, True, name, args)
            else:
                logging.info(
                    'no matches for log group %s in %s', name, matches)
    else:
        logger.error('failed to determine event type')
