import boto3
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def modify_subscription(client, is_create, logGroupName, filterName, destinationArn, deliveryRole):
    foundFilters = client.describe_subscription_filters(logGroupName=logGroupName)
    logger.info('log group %s has filters %s', logGroupName, foundFilters)
    
    filterExists = False
    for f in foundFilters['subscriptionFilters']:
        if is_create and f['destinationArn'] == destinationArn:
            return True  # A subscription to this destination ARN already exists
        if f['filterName'] == filterName:
          filterExists = True
    
    if is_create and not filterExists:
        try:
            client.put_subscription_filter(logGroupName=logGroupName,
                                            destinationArn=destinationArn,
                                            filterName=filterName,
                                            filterPattern='',
                                            roleArn=deliveryRole)
        except Exception as err:
            logger.error('Error adding subscription to log group %s: %s', logGroupName, err)
            return False
    
    if (not is_create) and filterExists:
        try:
            client.delete_subscription_filter(logGroupName=logGroupName,
                                              filterName=filterName)
        except Exception as err:
            logger.error('Error removing subscription from log group %s: %s', logGroupName, err)
            return False
    return True

def modify_subscriptions(client, is_create, prefix, filterName, destinationArn, deliveryRole):
    paginator = client.get_paginator('describe_log_groups')
    params = {'logGroupNamePrefix': prefix} if len(prefix) > 0 else {}
    
    successes, total = 0, 0
    for page in paginator.paginate(**params):
        for lg in page['logGroups']:
            success = modify_subscription(client, is_create, lg['logGroupName'], filterName, destinationArn, deliveryRole)
            successes, total = successes+(1 if success else 0), total+1
    
    return successes > 0 or total == 0

def main(event, context):
    isS3Event = 'Records' in event and 's3' in event['Records'][0]  # TODO: process multiple events
    
    prefix = os.environ['ALLOWED_LOG_GROUP_PREFIX']
    filterName = 'observe-collection-stack-' + os.environ['STACK_NAME']
    destinationArn = os.environ['DESTINATION_ARN']
    deliveryRole = os.environ['DELIVERY_STREAM_ROLE_ARN']
    
    logger.info('Event: %s', event)
    
    client = boto3.client('logs')
    if isS3Event:
        if event['Records'][0].get('eventName', "").startswith('ObjectCreated:'):
            _ = modify_subscriptions(client, True, prefix, filterName, destinationArn, deliveryRole)
        elif event['Records'][0].get('eventName', "").startswith('ObjectRemoved:'):
            _ = modify_subscriptions(client, False, prefix, filterName, destinationArn, deliveryRole)
    else:
        logGroupName = event['detail']['requestParameters']['logGroupName']
        if logGroupName.startswith(prefix):
            _ = modify_subscription(client, True, logGroupName, filterName, destinationArn, deliveryRole)