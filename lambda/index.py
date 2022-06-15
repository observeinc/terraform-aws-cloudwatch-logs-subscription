import dataclasses
import datetime
import json
import logging
import os
import re
import typing

import boto3

import cfnresponse

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# The lambda may create eventbridge events with values EVENTBRIDGE_SOURCE and
# EVENTBRIDGE_DETAIL_TYPE. If these variables are changed, the event pattern in
# aws_cloudwatch_event_rule.event_rule in main.tf should be changed too.
EVENTBRIDGE_SOURCE = "com.observeinc.autosubscribe"
EVENTBRIDGE_DETAIL_TYPE = "pagination"

# MAX_SUBSCRIPTIONS_PER_INVOCATION is the maximum number of subscriptions an invocation
# of main() will create or delete. This allows users to avoid hitting lambda timeouts.
MAX_SUBSCRIPTIONS_PER_INVOCATION = 100


@dataclasses.dataclass
class SubscriptionArgs:
    destination_arn: str
    filter_name: str
    filter_pattern: str
    role_arn: str


def modify_subscription(client, is_create: bool, log_group_name: str, subscription_args: SubscriptionArgs) -> bool:
    """modify_subscription creates or deletes a subscription filter for the log group specified by log_group_name

    if is_create is True, modify_subscription returns True if a subscription filter with the specified subscription_args exists (was created or already existed).
    if is_create is False, modify_subscription returns True if a subscription filter with the specified subscription_args does not exist (was deleted or did not exist).
    """
    logger.info('modify_subscription: %s %s %s',
                is_create, log_group_name, subscription_args)

    found_filters = client.describe_subscription_filters(
        logGroupName=log_group_name)
    logger.info('log group %s has filters %s', log_group_name, found_filters)

    filter_exists = False
    for f in found_filters['subscriptionFilters']:
        # TODO(luke): this doesn't ensure that subscription filters that weren't cleaned up properly get
        # the new arguments.
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


def should_subscribe(name: str, matches: list, exclusions: list) -> bool:
    """should_subscribe checks whether a log group with name 'name' should be subscribed to"""
    exclude = any([re.fullmatch(pattern, name)
                   for pattern in exclusions])
    if exclude:
        logging.info(
            'log group %s matches an exclusion regex pattern %s', name, exclusions)
    else:
        match = any([re.fullmatch(pattern, name)
                    for pattern in matches])
        if match:
            return True
        else:
            logging.info(
                'no matches for log group %s in %s', name, matches)
    return False


def modify_subscriptions(client, is_create: str, matches: list, exclusions: list, start_log_group: typing.Optional[str], subscription_args: SubscriptionArgs) -> typing.Tuple[typing.Optional[str], bool]:
    """modify_subscriptions creates or cleans up subscription filters for log groups that satisfy the
    lists of match and exclusion regex patterns. Exclusions have precedence over matches.

    modify_subscriptions creates subscription filters for at most MAX_SUBSCRIPTIONS_PER_INVOCATION log groups,
    starting with the log group specified by start_log_group.

    modify_subscriptions returns the name of the next subscription to be subscribed to, if any, and
    a boolean which is False if an error should be surfaced to the user.

    Subscriptions are created with subscription_args.
    """
    logger.info('modify_subscriptions: %s %s %s %s',
                is_create, matches, exclusions, subscription_args)

    # There are at most a few thousand log groups, so it should be ok to load them all into memory.
    log_groups = []
    paginator = client.get_paginator('describe_log_groups')
    for page in paginator.paginate():
        for lg in page['logGroups']:
            log_groups.append(lg)
    log_groups.sort(key=lambda lg: lg['logGroupName'])

    start_idx = 0
    if start_log_group is not None:
        for i, lg in enumerate(log_groups):
            name = lg['logGroupName']
            start_idx = i
            if name >= start_log_group:
                break

    successes, total = 0, 0
    next_log_group = None
    for lg in log_groups[start_idx:]:
        name = lg['logGroupName']
        if should_subscribe(name, matches, exclusions):
            if total >= MAX_SUBSCRIPTIONS_PER_INVOCATION:
                next_log_group = name
                break
            ok = modify_subscription(
                client, is_create, name, subscription_args)

            successes += 1 if ok else 0
            total += 1

    logger.info('succeeded updating (%d/%d) log groups matching patterns %s',
                successes, total, matches)

    if total > 0 and successes == 0:
        logger.error(
            'failed to successfully update any log groups, a major error may have occured')
        return None, False
    return next_log_group, True


def main(event, context):
    matchStr = os.environ['LOG_GROUP_MATCHES']
    exclusionStr = os.environ['LOG_GROUP_EXCLUDES']
    filter_name = os.environ['FILTER_NAME']
    filter_pattern = os.environ['FILTER_PATTERN']
    destination_rn = os.environ['DESTINATION_ARN']
    delivery_role = os.environ['DELIVERY_STREAM_ROLE_ARN']
    event_bus = os.environ['EVENTBRIDGE_EVENT_BUS']

    matches = matchStr.split(',') if matchStr != "" else []
    exclusions = exclusionStr.split(',') if exclusionStr != "" else []
    args = SubscriptionArgs(destination_rn, filter_name,
                            filter_pattern, delivery_role)

    logger.info('received event: %s', event)

    logsClient = boto3.client('logs')
    eventsClient = boto3.client('events')

    is_cfn_event = 'ResponseURL' in event
    is_pagination_event = 'source' in event and event['source'] == EVENTBRIDGE_SOURCE
    is_new_log_group_event = 'source' in event and event['source'] == 'aws.logs'
    if is_cfn_event or is_pagination_event:
        if is_cfn_event:
            cfnEvent = event
            start_log_group = None
        else:
            cfnEvent = event['detail']['cfnEvent']
            start_log_group = event['detail']['next']

        try:
            logger.info(
                'assuming event is a CloudFormation create or delete event')
            if cfnEvent['RequestType'] == 'Create':
                next_log_group, ok = modify_subscriptions(
                    logsClient, True, matches, exclusions, start_log_group, args)
            elif cfnEvent['RequestType'] == 'Delete':
                next_log_group, ok = modify_subscriptions(
                    logsClient, False, matches, exclusions, start_log_group, args)

            if ok:
                if next_log_group is None:
                    cfnresponse.send(cfnEvent, context,
                                     cfnresponse.SUCCESS, {})
                else:
                    logging.info(
                        'sending pagination event: next_log_group=%s', next_log_group)
                    entry = {
                        'Time': datetime.datetime.now(),
                        'Source': EVENTBRIDGE_SOURCE,
                        'DetailType': EVENTBRIDGE_DETAIL_TYPE,
                        'Detail': json.dumps({
                            'cfnEvent': cfnEvent,
                            'next': next_log_group,
                        }),
                        'EventBusName': event_bus,
                    }
                    eventsClient.put_events(Entries=[entry])
            else:
                data = {
                    'Data': 'Error: unable to create subscriptions for any log groups',
                }
                cfnresponse.send(cfnEvent, context, cfnresponse.FAILED, data)
        except Exception as e:
            logger.error('unexpected exception: %s', e)
            cfnresponse.send(event, context, cfnresponse.FAILED, {
                'Data': str(e)})
    elif is_new_log_group_event:
        logger.info('assuming event is an EventBridge event')
        if 'errorCode' in event['detail']:
            logger.info(
                'CreateLogGroup failed, cannot create subscription filter')
        else:
            name = event['detail']['requestParameters']['logGroupName']
            if should_subscribe(name, matches, exclusions):
                _ = modify_subscription(logsClient, True, name, args)
    else:
        logger.error('failed to determine event type')
