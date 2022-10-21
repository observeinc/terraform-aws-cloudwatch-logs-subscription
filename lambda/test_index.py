import dataclasses
import json
import typing
import unittest

from index import EVENTBRIDGE_SOURCE, MAX_SUBSCRIPTIONS_PER_INVOCATION, rest_of_main, SubscriptionArgs

# From https://docs.aws.amazon.com/lambda/latest/dg/services-cloudformation.html
FAKE_CFN_CREATE_EVENT = {
    "RequestType": "Create",
    "ServiceToken": "arn:aws:lambda:us-east-2:123456789012:function:lambda-error-processor-primer-14ROR2T3JKU66",
    "ResponseURL": "https://cloudformation-custom-resource-response-useast2.s3-us-east-2.amazonaws.com/arn%3Aaws%3Acloudformation%3Aus-east-2%3A123456789012%3Astack/lambda-error-processor/1134083a-2608-1e91-9897-022501a2c456%7Cprimerinvoke%7C5d478078-13e9-baf0-464a-7ef285ecc786?AWSAccessKeyId=AKIAIOSFODNN7EXAMPLE&Expires=1555451971&Signature=28UijZePE5I4dvukKQqM%2F9Rf1o4%3D",
    "StackId": "arn:aws:cloudformation:us-east-2:123456789012:stack/lambda-error-processor/1134083a-2608-1e91-9897-022501a2c456",
    "RequestId": "5d478078-13e9-baf0-464a-7ef285ecc786",
    "LogicalResourceId": "primerinvoke",
    "ResourceType": "AWS::CloudFormation::CustomResource",
    "ResourceProperties": {
        "ServiceToken": "arn:aws:lambda:us-east-2:123456789012:function:lambda-error-processor-primer-14ROR2T3JKU66",
        "FunctionName": "lambda-error-processor-randomerror-ZWUC391MQAJK"
    }
}

FAKE_CFN_DELETE_EVENT = {
    "RequestType": "Delete",
    "ServiceToken": "arn:aws:lambda:us-east-2:123456789012:function:lambda-error-processor-primer-14ROR2T3JKU66",
    "ResponseURL": "https://cloudformation-custom-resource-response-useast2.s3-us-east-2.amazonaws.com/arn%3Aaws%3Acloudformation%3Aus-east-2%3A123456789012%3Astack/lambda-error-processor/1134083a-2608-1e91-9897-022501a2c456%7Cprimerinvoke%7C5d478078-13e9-baf0-464a-7ef285ecc786?AWSAccessKeyId=AKIAIOSFODNN7EXAMPLE&Expires=1555451971&Signature=28UijZePE5I4dvukKQqM%2F9Rf1o4%3D",
    "StackId": "arn:aws:cloudformation:us-east-2:123456789012:stack/lambda-error-processor/1134083a-2608-1e91-9897-022501a2c456",
    "RequestId": "5d478078-13e9-baf0-464a-7ef285ecc786",
    "LogicalResourceId": "primerinvoke",
    "ResourceType": "AWS::CloudFormation::CustomResource",
    "ResourceProperties": {
        "ServiceToken": "arn:aws:lambda:us-east-2:123456789012:function:lambda-error-processor-primer-14ROR2T3JKU66",
        "FunctionName": "lambda-error-processor-randomerror-ZWUC391MQAJK"
    }
}


@dataclasses.dataclass
class FakeContext:
    log_stream_name: str


FAKE_CONTEXT = FakeContext("fake-log-stream-name")


class FakeWrapper:
    """FakeWrapper is a AWSWrapper mock."""

    def __init__(self, log_groups: typing.List[str], subscription_filters: typing.Dict[str, typing.List[SubscriptionArgs]]) -> None:
        self.log_groups = log_groups
        self.subscription_filters = subscription_filters
        self.record = []

    def describe_log_groups_paginator(self):
        self.record.append([
            "describe_log_groups_paginator",
        ])

        class FakePaginator:
            def __init__(self, log_groups) -> None:
                self.log_groups = log_groups

            def paginate(self):
                return [{"logGroups": [{"logGroupName": name} for name in self.log_groups]}]
        return FakePaginator(self.log_groups)

    def describe_subscription_filters(self, **kwargs):
        self.record.append([
            "describe_subscription_filters",
            kwargs
        ])

        log_group_name = kwargs["logGroupName"]
        args = self.subscription_filters.get(log_group_name, [])
        return {
            "subscriptionFilters": [{
                "filterName": arg.filter_name,
                "filterPattern": arg.filter_pattern,
                "destinationArn": arg.destination_arn,
                "roleArn": arg.role_arn,
            } for arg in args]
        }

    def put_subscription_filter(self, **kwargs):
        self.record.append([
            "put_subscription_filter",
            kwargs
        ])
        args = SubscriptionArgs(
            kwargs['destinationArn'], kwargs['filterName'], kwargs['filterPattern'], kwargs['roleArn'])
        if kwargs['logGroupName'] in self.subscription_filters:
            self.subscription_filters[kwargs['logGroupName']].append(args)
        else:
            self.subscription_filters[kwargs['logGroupName']] = [args]

    def delete_subscription_filter(self, **kwargs):
        self.record.append([
            "delete_subscription_filter",
            kwargs
        ])
        if kwargs['logGroupName'] in self.subscription_filters:
            self.subscription_filters[kwargs['logGroupName']] = [
                a for a in self.subscription_filters[kwargs['logGroupName']] if a.filter_name != kwargs['filterName']]
            if len(self.subscription_filters[kwargs['logGroupName']]) == 0:
                del self.subscription_filters[kwargs['logGroupName']]

    def put_events(self, **kwargs):
        self.record.append([
            "put_events",
            kwargs
        ])

    def send_cfnresponse(self, event, responseStatus, responseData, physicalResourceId=None, noEcho=False, reason=None):
        self.record.append([
            "send_cfnresponse",
            event, responseStatus, responseData, physicalResourceId, noEcho, reason,
        ])


class TestRestOfMain(unittest.TestCase):
    """TestRestOfMain contains test cases for the code in rest_of_main.

    This code exists as an alternative to testing by manually applying a
    Cloudformation or terraform template.
    """

    def __init__(self, methodName: str = ...) -> None:
        # I set self.maxDiff to None so that we can see long diffs.
        self.maxDiff = None
        super().__init__(methodName)

    def test_create_delete(self):
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        log_groups = [
            "/aws/lambda/func1",
            "/aws/lambda/func2",
            "/aws/bean/nginx1",
        ]
        wrapper = FakeWrapper(log_groups=log_groups,
                              subscription_filters={})
        matches = [".*"]
        exclusions = []
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        timeout = 10

        rest_of_main(FAKE_CFN_CREATE_EVENT,
                     wrapper, matches, exclusions, args, timeout)

        expected = {'/aws/bean/nginx1': [SubscriptionArgs(destination_arn='fake-destination-arn', filter_name='my-filter', filter_pattern='', role_arn='fake-role-arn')],
                    '/aws/lambda/func1': [SubscriptionArgs(destination_arn='fake-destination-arn', filter_name='my-filter', filter_pattern='', role_arn='fake-role-arn')],
                    '/aws/lambda/func2': [SubscriptionArgs(destination_arn='fake-destination-arn', filter_name='my-filter', filter_pattern='', role_arn='fake-role-arn')]}
        self.assertEqual(wrapper.subscription_filters, expected)

        rest_of_main(FAKE_CFN_DELETE_EVENT,
                     wrapper, matches, exclusions, args, timeout)
        self.assertEqual(wrapper.subscription_filters, {})

    def test_new_log_group(self):
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        log_groups = [
            "/aws/lambda/func1",
            "/aws/lambda/func2",
            "/aws/bean/nginx1",
        ]
        wrapper = FakeWrapper(log_groups=log_groups,
                              subscription_filters={})
        matches = [".*"]
        exclusions = []
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        timeout = 10

        create_log_group_event = {
            "source": "aws.logs",
            "detail": {
                "requestParameters": {
                    "logGroupName": "/aws/bean/nginx1",
                }
            }
        }

        rest_of_main(create_log_group_event,
                     wrapper, matches, exclusions, args, timeout)
        expected = {'/aws/bean/nginx1': [SubscriptionArgs(
            destination_arn='fake-destination-arn', filter_name='my-filter', filter_pattern='', role_arn='fake-role-arn')]}
        self.assertEqual(wrapper.subscription_filters, expected)

    def test_new_log_group_bad_event(self):
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        log_groups = [
            "/aws/lambda/func1",
            "/aws/lambda/func2",
            "/aws/bean/nginx1",
        ]
        wrapper = FakeWrapper(log_groups=log_groups,
                              subscription_filters={})
        matches = [".*"]
        exclusions = []
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        timeout = 10

        create_log_group_event = {
            "source": "aws.logs",
            "detail": {
                "errorCode": 400,
            }
        }

        rest_of_main(create_log_group_event,
                     wrapper, matches, exclusions, args, timeout)
        self.assertEqual(wrapper.subscription_filters, {})

    def test_matches_and_exclusions(self):
        tcs = [{
            # simple match
            "matches": [".*"],
            "exclusions": [],
            "expected": {"/aws/lambda/func1", "/aws/lambda/func2", "/aws/bean/nginx1"},
        },
            # simple exclusion
            {
            "matches": [".*"],
            "exclusions": ["/aws/bean/.*"],
            "expected": {"/aws/lambda/func1", "/aws/lambda/func2"},
        },
            # multiple matches
            {
            "matches": ["/aws/lambda/func1", "/aws/lambda/func2"],
            "exclusions": [""],
            "expected": {"/aws/lambda/func1", "/aws/lambda/func2"},
        }]

        for case in tcs:
            wrapper = FakeWrapper(log_groups=[
                "/aws/lambda/func1",
                "/aws/lambda/func2",
                "/aws/bean/nginx1",
            ], subscription_filters={})
            args = SubscriptionArgs("fake-destination-arn",
                                    "my-filter", "", "fake-role-arn")
            timeout = 10

            rest_of_main(FAKE_CFN_CREATE_EVENT,
                         wrapper, case["matches"], case["exclusions"], args, timeout)
            actual = {r[1]["logGroupName"]
                      for r in wrapper.record
                      if r[0] == "put_subscription_filter"}
            self.assertEqual(case["expected"], actual)

    def test_subscription_args(self):
        tcs = [{
            "args": SubscriptionArgs('fake-destination-arn', 'my-filter', 'my-filter-pattern', 'fake-role-arn'),
            "expected": {
                'destinationArn': 'fake-destination-arn',
                'filterName': 'my-filter',
                'filterPattern': 'my-filter-pattern',
                'roleArn': 'fake-role-arn'
            },
        }]
        for case in tcs:
            wrapper = FakeWrapper(log_groups=[
                "/aws/lambda/func1",
                "/aws/lambda/func2",
                "/aws/bean/nginx1",
            ], subscription_filters={})
            matches = [".*"]
            exclusions = []

            timeout = 10

            rest_of_main(FAKE_CFN_CREATE_EVENT,
                         wrapper, matches, exclusions, case["args"], timeout)

            def without_keys(d, keys):
                return {k: v for k, v in d.items() if k not in keys}

            actual = [without_keys(r[1], "logGroupName")
                      for r in wrapper.record
                      if r[0] == "put_subscription_filter"]

            for x in actual:
                self.assertEqual(case["expected"], x)

    def test_cfn_response_success(self):
        log_groups = [
            "/aws/lambda/func1",
            "/aws/lambda/func2",
            "/aws/bean/nginx1",
        ]
        wrapper = FakeWrapper(log_groups=log_groups, subscription_filters={})
        matches = [".*"]
        exclusions = []
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        timeout = 10

        rest_of_main(FAKE_CFN_CREATE_EVENT,
                     wrapper, matches, exclusions, args, timeout)

        last_record = wrapper.record[-1]
        self.assertEqual(last_record[0], "send_cfnresponse")
        self.assertEqual(last_record[1], FAKE_CFN_CREATE_EVENT)
        self.assertEqual(last_record[2], "SUCCESS")

    def test_cfn_response_failure(self):
        class FakeFailWrapper(FakeWrapper):
            def describe_subscription_filters(self, **kwargs):
                raise Exception()

        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        log_groups = [
            "/aws/lambda/func1",
            "/aws/lambda/func2",
            "/aws/bean/nginx1",
        ]
        wrapper = FakeFailWrapper(log_groups=log_groups,
                                  subscription_filters={})
        matches = [".*"]
        exclusions = []

        timeout = 10

        rest_of_main(FAKE_CFN_CREATE_EVENT,
                     wrapper, matches, exclusions, args, timeout)

        last_record = wrapper.record[-1]
        self.assertEqual(last_record[0], "send_cfnresponse")
        self.assertEqual(last_record[1], FAKE_CFN_CREATE_EVENT)
        self.assertEqual(last_record[2], "FAILED")

    def test_pagination(self):
        log_groups = [
            f"/aws/lambda/func{i}" for i in range(MAX_SUBSCRIPTIONS_PER_INVOCATION + 1)]
        wrapper = FakeWrapper(log_groups=log_groups, subscription_filters={})
        matches = [".*"]
        exclusions = []
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        timeout = 10

        rest_of_main(FAKE_CFN_CREATE_EVENT,
                     wrapper, matches, exclusions, args, timeout)

        last_record = wrapper.record[-1]
        self.assertEqual(last_record[0], "put_events")
        self.assertEqual(last_record[1]['Entries']
                         [0]['Source'], EVENTBRIDGE_SOURCE)
        self.assertEqual(last_record[1]['Entries'][0]['Detail'], json.dumps({
            'cfnEvent': FAKE_CFN_CREATE_EVENT,
            'next': "/aws/lambda/func99",
        }))

        # The eventbridge event then triggers another lambda call with the data
        # in the following form.
        eventBridgeEvent = {
            "source": last_record[1]['Entries'][0]['Source'],
            "detail": json.loads(last_record[1]['Entries'][0]['Detail']),
        }
        rest_of_main(eventBridgeEvent,
                     wrapper, matches, exclusions, args, timeout)

        self.assertTrue(len(last_record) > 0)
        last_record = wrapper.record[-1]
        self.assertEqual(last_record[0], "send_cfnresponse")

    def test_idempotency(self):
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")

        log_groups = [
            "/aws/lambda/func1",
            "/aws/lambda/func2",
            "/aws/bean/nginx1",
        ]
        subscription_filters = {
            "/aws/lambda/func1": [args]
        }
        wrapper = FakeWrapper(log_groups=log_groups,
                              subscription_filters=subscription_filters)
        matches = [".*"]
        exclusions = []
        args = SubscriptionArgs("fake-destination-arn",
                                "my-filter", "", "fake-role-arn")
        timeout = 10

        rest_of_main(FAKE_CFN_CREATE_EVENT,
                     wrapper, matches, exclusions, args, timeout)

        expected = {'/aws/bean/nginx1': [SubscriptionArgs(destination_arn='fake-destination-arn', filter_name='my-filter', filter_pattern='', role_arn='fake-role-arn')],
                    '/aws/lambda/func1': [SubscriptionArgs(destination_arn='fake-destination-arn', filter_name='my-filter', filter_pattern='', role_arn='fake-role-arn')],
                    '/aws/lambda/func2': [SubscriptionArgs(destination_arn='fake-destination-arn', filter_name='my-filter', filter_pattern='', role_arn='fake-role-arn')]}
        self.assertEqual(wrapper.subscription_filters, expected)


if __name__ == '__main__':
    unittest.main()
