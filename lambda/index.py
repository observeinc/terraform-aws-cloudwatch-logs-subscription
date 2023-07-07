import dataclasses
import datetime
import json
import logging
import os
import re
import typing
import time
import threading
import traceback

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
# of main() will create or delete. This allows users to avoid hitting
# lambda timeouts.
MAX_SUBSCRIPTIONS_PER_INVOCATION = 100

# If our code generates an exception on rollback (delete), the user will need to go to the UI
# to manually delete the CloudFormation Stack. IGNORE_DELETE_ERRORS allows the user to
# delete the stack without going to the UI.
ignore_delete_errors = os.environ['IGNORE_DELETE_ERRORS']


@dataclasses.dataclass
class SubscriptionArgs:
    destination_arn: str
    filter_name: str
    filter_pattern: str
    role_arn: str


class AWSWrapper:
    """AWSWrapper talks to AWS.

    This class exists so that we can write unit tests, which exist to reduce the
    cost of changing code.

    The code for this class should be simple since it is not easy to test the
    wrapper implementation itself.
    """
    pass

    def __init__(self, logs_client, events_client, context) -> None:
        self.logs_client = logs_client
        self.events_client = events_client
        self.context = context

    def describe_log_groups_paginator(self):
        return self.logs_client.get_paginator('describe_log_groups')

    def describe_subscription_filters(self, **kwargs):
        return self.logs_client.describe_subscription_filters(**kwargs)

    def put_subscription_filter(self, **kwargs):
        return self.logs_client.put_subscription_filter(**kwargs)

    def delete_subscription_filter(self, **kwargs):
        return self.logs_client.delete_subscription_filter(**kwargs)

    def put_events(self, **kwargs):
        return self.events_client.put_events(**kwargs)

    def send_cfnresponse(
            self,
            event,
            responseStatus,
            responseData,
            physicalResourceId=None,
            noEcho=False,
            reason=None):
        if ignore_delete_errors and event['RequestType'] == 'Delete':
            responseStatus = cfnresponse.SUCCESS
        return cfnresponse.send(
            event,
            self.context,
            responseStatus,
            responseData,
            physicalResourceId=physicalResourceId,
            noEcho=noEcho,
            reason=reason)


def modify_subscription(
        client_wrapper: AWSWrapper,
        is_create: bool,
        log_group_name: str,
        subscription_args: SubscriptionArgs) -> bool:
    """modify_subscription creates or deletes a subscription filter for the log group specified by log_group_name

    if is_create is True, modify_subscription returns True if a subscription filter with the specified subscription_args exists (was created or already existed).
    if is_create is False, modify_subscription returns True if a subscription filter with the specified subscription_args does not exist (was deleted or did not exist).
    """
    logger.info('modify_subscription: %s %s %s',
                is_create, log_group_name, subscription_args)

    found_filters = client_wrapper.describe_subscription_filters(
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
            client_wrapper.put_subscription_filter(
                logGroupName=log_group_name,
                destinationArn=subscription_args.destination_arn,
                filterName=subscription_args.filter_name,
                filterPattern=subscription_args.filter_pattern,
                roleArn=subscription_args.role_arn)
            logger.info('created subscription filter %s for log group %s',
                        subscription_args.filter_name, log_group_name)
        except Exception as err:
            logger.error(
                'error adding subscription to log group %s: %s',
                log_group_name,
                err)
            return False

    if (not is_create) and filter_exists:
        try:
            client_wrapper.delete_subscription_filter(
                logGroupName=log_group_name,
                filterName=subscription_args.filter_name)
            logger.info('deleted subscription filter %s for log group %s',
                        subscription_args.filter_name, log_group_name)
        except Exception as err:
            logger.error(
                'error removing subscription from log group %s: %s',
                log_group_name,
                err)
            return False
    return True


def should_subscribe(
        name: str,
        matches: typing.List[str],
        exclusions: typing.List[str]) -> bool:
    """should_subscribe checks whether a log group with name 'name' should be subscribed to"""
    exclude = any([re.fullmatch(pattern, name)
                   for pattern in exclusions])
    if exclude:
        logging.info(
            'log group %s matches an exclusion regex pattern %s',
            name,
            exclusions)
    else:
        match = any([re.fullmatch(pattern, name)
                    for pattern in matches])
        if match:
            return True
        else:
            logging.info(
                'no matches for log group %s in %s', name, matches)
    return False


def modify_subscriptions(client_wrapper: AWSWrapper,
                         is_create: str,
                         matches: list,
                         exclusions: list,
                         start_log_group: typing.Optional[str],
                         subscription_args: SubscriptionArgs) -> typing.Tuple[typing.Optional[str],
                                                                              bool]:
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

    # There are at most a few thousand log groups, so it should be ok to load
    # them all into memory.
    log_groups = []
    paginator = client_wrapper.describe_log_groups_paginator()
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
                client_wrapper, is_create, name, subscription_args)

            successes += 1 if ok else 0
            total += 1

    logger.info('succeeded updating (%d/%d) log groups matching patterns %s',
                successes, total, matches)

    if total > 0 and successes == 0:
        logger.error(
            'failed to successfully update any log groups, a major error may have occured')
        return None, False
    return next_log_group, True


def process_setup_event(
        client_wrapper: AWSWrapper,
        cfn_event,
        start_log_group: typing.Optional[str],
        matches: typing.List[str],
        exclusions: typing.List[str],
        args: SubscriptionArgs):
    try:
        logger.info(
            'assuming event is a CloudFormation create or delete event')
        if cfn_event['RequestType'] == 'Create':
            next_log_group, ok = modify_subscriptions(
                client_wrapper, True, matches, exclusions, start_log_group, args)
        elif cfn_event['RequestType'] == 'Delete':
            next_log_group, ok = modify_subscriptions(
                client_wrapper, False, matches, exclusions, start_log_group, args)

        if ok:
            if next_log_group is None:
                client_wrapper.send_cfnresponse(
                    cfn_event, cfnresponse.SUCCESS, {})
            else:
                logging.info(
                    'sending pagination event: next_log_group=%s',
                    next_log_group)
                entry = {
                    'Time': datetime.datetime.now(),
                    'Source': EVENTBRIDGE_SOURCE,
                    'DetailType': EVENTBRIDGE_DETAIL_TYPE,
                    'Detail': json.dumps({
                        'cfnEvent': cfn_event,
                        'next': next_log_group,
                    }),
                }
                client_wrapper.put_events(Entries=[entry])
        else:
            data = {
                'Data': 'Error: unable to create subscriptions for any log groups', }
            client_wrapper.send_cfnresponse(
                cfn_event, cfnresponse.FAILED, data)
    except Exception as e:
        logger.error('unexpected exception: %s', e)
        traceback.print_exc()
        client_wrapper.send_cfnresponse(cfn_event, cfnresponse.FAILED, {
            'Error': str(e)})


def send_cfnresponse_5s_before_timeout(
        client_wrapper: AWSWrapper,
        timeout_seconds: int,
        cfn_event):
    time.sleep(timeout_seconds - 5)
    data = {
        'Data': 'Error: Lambda Function probably would have timed out. If the subscription process was close to completing, consider increasing the timeout.',
    }
    client_wrapper.send_cfnresponse(cfn_event, cfnresponse.FAILED, data)


def rest_of_main(
        event,
        client_wrapper: AWSWrapper,
        matches: typing.List[str],
        exclusions: typing.List[str],
        args: SubscriptionArgs,
        timeout: int):
    """rest_of_main is supposed to be testable. It should not call client_wrapper"""

    is_cfn_event = 'ResponseURL' in event
    is_pagination_event = 'source' in event and event['source'] == EVENTBRIDGE_SOURCE
    is_new_log_group_event = 'source' in event and event['source'] == 'aws.logs'
    if is_cfn_event or is_pagination_event:
        if is_cfn_event:
            cfn_event = event
            start_log_group = None
        else:
            cfn_event = event['detail']['cfnEvent']
            start_log_group = event['detail']['next']

        # This code exists so that lambda failures don't fail silently and indefinitely block
        # the CloudFormation stack creation progress. Instead, this code tries to make it so that users
        # actually get feedback if something goes wrong, saving them ~30 minutes.
        #
        # If the main thread completes in time, the lambda exits once the main thread is done
        # and a successful response is sent to CloudFormation.
        # If the main thread doesn't complete in time, cancel_thread hopefully completes
        # and sends a response to CloudFormation before the Lambda execution environment is killed.
        #
        # If the cancel thread completes, then it's likely that the CloudFormation stack that
        # calls this code will trigger a rollback. Deletion is likely to time out as well since
        # the same code path is executed, resulting in an incomplete cleanup. Incomplete cleanup
        # is fine, since the lambda code knows how to deal with it. A user just needs to rerun the
        # CloudFormation stack or Terraform module with a larger timeout.
        #
        # If some exception occurs, then we send a cfnresponse so that the CloudFormation stack does not hang.
        #
        # There is a chance of a race condition where we send 2 responses to CloudFormation. This
        # case is unlikely. It also doesn't result in incomplete setup for the
        # customer.
        try:
            main_thread = threading.Thread(
                target=process_setup_event,
                args=(
                    client_wrapper,
                    cfn_event,
                    start_log_group,
                    matches,
                    exclusions,
                    args))
            cancel_thread = threading.Thread(
                target=send_cfnresponse_5s_before_timeout, args=(
                    client_wrapper, timeout, cfn_event))
            main_thread.start()
            cancel_thread.start()
            main_thread.join()
        except Exception as e:
            logger.error('unexpected exception: %s', e)
            traceback.print_exc()
            client_wrapper.send_cfnresponse(cfn_event, cfnresponse.FAILED, {
                'Error': str(e)})
    elif is_new_log_group_event:
        logger.info('assuming event is an CreateLogGroup Eventbridge event')
        if 'errorCode' in event['detail']:
            logger.info(
                'CreateLogGroup failed, cannot create subscription filter')
        else:
            name = event['detail']['requestParameters']['logGroupName']
            if should_subscribe(name, matches, exclusions):
                _ = modify_subscription(client_wrapper, True, name, args)
    else:
        logger.error('failed to determine event type')


def main(event, context):
    """main is expected the Lambda handler method. It responds to an Lambda Event
    by either creating or deleting 1+ CloudWatch Log Subscription Filters.

    See (https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-concepts.html#gettingstarted-concepts-event)
    for more info on an event.

    If the event is a CloudFormation Customer Resource Create event, main scans through
    all log groups and creates subscription filters. Subscr

    If the event is a CloudFormation Customer Resource Delete event, main scans through
    all log groups and deletes subscription filters.

    If the event is an EventBridge event from a CreateLogGroup AWS API call, main creates
    a subscription filter for that log group.


    Whether a subscription filter gets created is controlled by the following environment variables:
    - LOG_GROUP_MATCHES
    - LOG_GROUP_EXCLUDES

    The Subscription filter configuration is controlled by the following environment variables:
    - FILTER_NAME
    - FILTER_PATTERN
    - DESTINATION_ARN
    - DELIVERY_STREAM_ROLE_ARN

    The timeout environment variable is supposed to be the lambda timeout. It exists to prevent
    the issue described in https://observe.atlassian.net/browse/OB-12739.

    See relevant terraform variables for a description of what these variables are supposed to do.
    """
    matchStr = os.environ['LOG_GROUP_MATCHES']
    exclusionStr = os.environ['LOG_GROUP_EXCLUDES']
    filter_name = os.environ['FILTER_NAME']
    filter_pattern = os.environ['FILTER_PATTERN']
    destination_arn = os.environ['DESTINATION_ARN']
    delivery_role = os.environ['DELIVERY_STREAM_ROLE_ARN']
    timeout = os.environ['TIMEOUT']

    matches = matchStr.split(',') if matchStr != "" else []
    exclusions = exclusionStr.split(',') if exclusionStr != "" else []
    args = SubscriptionArgs(destination_arn, filter_name,
                            filter_pattern, delivery_role)
    timeout = int(timeout)

    logger.info('received event: %s', event)

    client_wrapper = AWSWrapper(boto3.client(
        'logs'), boto3.client('events'), context)

    rest_of_main(event, client_wrapper, matches, exclusions, args, timeout)
