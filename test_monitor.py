import io
import json
import unittest
from unittest.mock import Mock

from monitor import INCIDENT, DELIVERY_TEST, RepositoryAlerts, check, probe


class Response(io.BytesIO):
    status = 200


def opener(payload, status=200):
    response = Response(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
    response.status = status
    return Mock(open=Mock(return_value=response))


class MonitorTests(unittest.TestCase):
    def test_three_health_endpoints_and_readiness_database(self):
        self.assertTrue(probe('/health/live', opener({'ok': True})))
        self.assertTrue(probe('/health/worker', opener({'ok': True})))
        self.assertFalse(probe('/health/ready', opener({'ok': True})))
        self.assertTrue(probe('/health/ready', opener({'ok': True, 'database': 'ok'})))

    def test_fail_closed_on_invalid_large_or_non_success_responses(self):
        for payload, status in [(b'not json', 200), (b'x'*4097, 200), ({'ok': True}, 302),
                                ({'ok': False}, 200), ([], 200), ({'ok': 'true'}, 200)]:
            self.assertFalse(probe('/health/live', opener(payload, status)))
        with self.assertRaises(ValueError):
            probe('https://other.example/private')

    def test_bounded_retry_and_transient_recovery(self):
        calls, pauses = [], []
        def transient(path):
            calls.append(path)
            return path != '/health/ready' or calls.count(path) == 3
        self.assertTrue(all(check(transient, pauses.append).values()))
        self.assertEqual(len(calls), 5)
        self.assertEqual(pauses, [3, 3])
        calls.clear()
        self.assertFalse(any(check(lambda path: calls.append(path) or False, lambda _: None).values()))
        self.assertEqual(len(calls), 9)

    def test_alert_token_cannot_be_sent_to_another_repository_or_url(self):
        with self.assertRaises(ValueError):
            RepositoryAlerts('synthetic', 'other/repository')
        alerts = RepositoryAlerts('synthetic', 'nitzantzadok/geominate-availability')
        with self.assertRaises(ValueError):
            alerts.api('POST', '/issues/1/../../private')

    def test_incident_deduplication_and_owner_assignment(self):
        alerts = RepositoryAlerts('synthetic', 'nitzantzadok/geominate-availability')
        alerts.api = Mock(side_effect=[[], {'number': 7}])
        self.assertEqual(alerts.notify(INCIDENT, 'public health check failed'), 7)
        payload = alerts.api.call_args_list[1].args[2]
        self.assertEqual(payload['assignees'], ['nitzantzadok'])
        alerts.api = Mock(return_value=[{'title': INCIDENT, 'number': 7,
                                       'user': {'login': 'github-actions[bot]'}}])
        self.assertEqual(alerts.notify(INCIDENT, 'retry'), 7)
        self.assertEqual(alerts.api.call_count, 1)

    def test_recovery_never_closes_human_issues_or_delivery_tests(self):
        alerts = RepositoryAlerts('synthetic', 'nitzantzadok/geominate-availability')
        alerts.api = Mock(return_value=[{'title': INCIDENT, 'number': 2,
                                       'user': {'login': 'human'}},
                                      {'title': DELIVERY_TEST, 'number': 3,
                                       'user': {'login': 'github-actions[bot]'}}])
        alerts.recovered('2026-11-21T00:00:00Z')
        self.assertEqual(alerts.api.call_count, 1)


if __name__ == '__main__':
    unittest.main()
