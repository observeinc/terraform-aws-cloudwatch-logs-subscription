import dataclasses
import json
import logging
import os

import boto3

import cfnresponse

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@dataclasses.dataclass
class SubscriptionArgs:
    destinationArn: str
    filterName: str
    filterPattern: str
    roleArn: str


def modify_subscription(client, is_create: bool, logGroupName: str, subscriptionArgs: SubscriptionArgs):
    logger.info('modify_subscription: %s %s %s',
                is_create, logGroupName, subscriptionArgs)

    foundFilters = client.describe_subscription_filters(
        logGroupName=logGroupName)
    logger.info('log group %s has filters %s', logGroupName, foundFilters)

    filterExists = False
    for f in foundFilters['subscriptionFilters']:
        if is_create and f['destinationArn'] == subscriptionArgs.destinationArn:
            return True  # A subscription to this destination ARN already exists
        if f['filterName'] == subscriptionArgs.filterName:
            filterExists = True

    if is_create and (not filterExists):
        try:
            client.put_subscription_filter(logGroupName=logGroupName,
                                           destinationArn=subscriptionArgs.destinationArn,
                                           filterName=subscriptionArgs.filterName,
                                           filterPattern=subscriptionArgs.filterPattern,
                                           roleArn=subscriptionArgs.roleArn)
            logger.info('created subscription filter %s for log group %s',
                        subscriptionArgs.filterName, logGroupName)
        except Exception as err:
            logger.error(
                'error adding subscription to log group %s: %s', logGroupName, err)
            return False

    if (not is_create) and filterExists:
        try:
            client.delete_subscription_filter(logGroupName=logGroupName,
                                              filterName=subscriptionArgs.filterName)
            logger.info('deleted subscription filter %s for log group %s',
                        subscriptionArgs.filterName, logGroupName)
        except Exception as err:
            logger.error(
                'error removing subscription from log group %s: %s', logGroupName, err)
            return False
    return True


def modify_subscriptions(client, is_create: str, prefixes: list, subscriptionArgs: SubscriptionArgs):
    logger.info('modify_subscriptions: %s %s %s',
                is_create, prefixes, subscriptionArgs)

    successes, total = 0, 0
    for prefix in prefixes:
        paginator = client.get_paginator('describe_log_groups')
        params = {'logGroupNamePrefix': prefix} if len(prefix) > 0 else {}

        for page in paginator.paginate(**params):
            for lg in page['logGroups']:
                success = modify_subscription(
                    client, is_create, lg['logGroupName'], subscriptionArgs)
                successes, total = successes+(1 if success else 0), total+1

    logger.info('succeeeded updating (%d/%d) log groups matching prefixes %s',
                successes, total, prefixes)
    return successes > 0 or total == 0


def main(event, context):
    prefixes = json.loads(os.environ['LOG_GROUP_PREFIXES'])
    filterName = os.environ['FILTER_NAME']
    filterPattern = os.environ['FILTER_PATTERN']
    destinationArn = os.environ['DESTINATION_ARN']
    deliveryRole = os.environ['DELIVERY_STREAM_ROLE_ARN']

    args = SubscriptionArgs(destinationArn, filterName,
                            filterPattern, deliveryRole)

    logger.info('received event: %s', event)

    client = boto3.client('logs')

    isCfnEvent = 'ResponseURL' in event
    isEventBridgeEvent = 'detail' in event
    if isCfnEvent:
        try:
            logger.info(
                'assuming event is a CloudFormation create or delete event')
            anySuccesses = False
            if event['RequestType'] == 'Create':
                anySuccesses = modify_subscriptions(
                    client, True, prefixes, args)
            elif event['RequestType'] == 'Delete':
                anySuccesses = modify_subscriptions(
                    client, False, prefixes, args)

            if anySuccesses:
                cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            else:
                cfnresponse.send(event, context, cfnresponse.FAILED, {
                                 'Data': 'Error: unable to create subscriptions for any log groups'})
        except Exception as e:
            logger.error('unexpected exception: %s', e)
            cfnresponse.send(event, context, cfnresponse.FAILED, {
                'Data': str(e)})
    elif isEventBridgeEvent:
        logger.info('assuming event is an EventBridge event')
        logGroupName = event['detail']['requestParameters']['logGroupName']
        for prefix in prefixes:
            if logGroupName.startswith(prefix):
                _ = modify_subscription(client, True, logGroupName, args)
    else:
        logger.error('failed to determine event type')
