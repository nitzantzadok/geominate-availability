"""Public, credential-free website probes; optional repo-local incident alerts."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ORIGIN = 'https://geominate.com'
PATHS = ('/health/live', '/health/ready', '/health/worker')
REPOSITORY = 'nitzantzadok/geominate-availability'
INCIDENT = '[GEOminate] Availability incident'
DELIVERY_TEST = '[GEOminate] Alert delivery test — no production failure'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(path, opener=None):
    if path not in PATHS:
        raise ValueError('unsupported endpoint')
    opener = opener or urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(ORIGIN + path, headers={
        'Accept': 'application/json', 'User-Agent': 'GEOminate-availability/1.0'})
    try:
        with opener.open(request, timeout=8) as response:
            body = response.read(4097)
            if response.status != 200 or len(body) > 4096:
                return False
            value = json.loads(body)
            return (isinstance(value, dict) and value.get('ok') is True
                    and (path != '/health/ready' or value.get('database') == 'ok'))
    except (OSError, ValueError, TypeError):
        return False


def check(probe_fn=probe, pause=time.sleep):
    results = {}
    for path in PATHS:
        for attempt in range(3):
            results[path] = bool(probe_fn(path))
            if results[path]:
                break
            if attempt < 2:
                pause(3)
    return results


class RepositoryAlerts:
    def __init__(self, token, repository, opener=None):
        if repository != REPOSITORY or not token:
            raise ValueError('repository-local alert configuration is missing')
        self.token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def api(self, method, path, data=None):
        if not re.fullmatch(r'/issues(?:/[1-9][0-9]*(?:/comments)?)?(?:\?state=open&per_page=100)?', path):
            raise ValueError('unsupported repository operation')
        request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + path,
            data=json.dumps(data).encode() if data is not None else None,
            method=method, headers={'Authorization': 'Bearer ' + self.token,
                'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
                'User-Agent': 'GEOminate-availability/1.0', 'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with self.opener.open(request, timeout=10) as response:
                raw = response.read(512001)
                if len(raw) > 512000:
                    raise RuntimeError('alert response too large')
                return json.loads(raw)
        except (OSError, ValueError) as exc:
            raise RuntimeError('repository alert request did not complete') from None

    def open_issue(self, title):
        issues = self.api('GET', '/issues?state=open&per_page=100')
        if not isinstance(issues, list) or len(issues) >= 100:
            raise RuntimeError('incident inventory requires operator review')
        return next((item for item in issues if item.get('title') == title
            and not item.get('pull_request')
            and item.get('user', {}).get('login') == 'github-actions[bot]'
            and type(item.get('number')) is int and item['number'] > 0), None)

    def notify(self, title, body):
        if title not in {INCIDENT, DELIVERY_TEST}:
            raise ValueError('unsupported alert type')
        issue = self.open_issue(title)
        if issue:
            return issue['number']
        issue = self.api('POST', '/issues', {'title': title, 'body': body,
                                            'assignees': ['nitzantzadok']})
        number = issue.get('number') if isinstance(issue, dict) else None
        if type(number) is not int or number < 1:
            raise RuntimeError('alert creation was not confirmed')
        return number

    def recovered(self, at):
        issue = self.open_issue(INCIDENT)
        if not issue:
            return
        self.api('POST', '/issues/' + str(issue['number']) + '/comments',
                 {'body': 'All three public health checks passed at ' + at + '.'})
        self.api('PATCH', '/issues/' + str(issue['number']),
                 {'state': 'closed', 'state_reason': 'completed'})


def main():
    mode = os.environ.get('MONITOR_MODE', 'probe')
    if mode not in {'probe', 'alert-test'}:
        raise ValueError('unsupported mode')
    at = datetime.now(timezone.utc).isoformat()
    alerts = RepositoryAlerts(os.environ.get('GH_TOKEN', ''), os.environ.get('GITHUB_REPOSITORY', ''))
    if mode == 'alert-test':
        number = alerts.notify(DELIVERY_TEST,
            'Intentional alert-delivery test at ' + at + '.\n\n'
            'The production application was not changed or interrupted. '
            'This issue was assigned to the repository owner to test GitHub notification delivery. '
            'Inbox or email delivery must be observed separately before claiming that it works.')
        print(json.dumps({'mode': mode, 'issue': number, 'production_changed': False}))
        return
    results = check()
    print(json.dumps({'checked_at': at, 'healthy': all(results.values()), 'endpoints': results}))
    if all(results.values()):
        alerts.recovered(at)
    else:
        failures = [path for path, ok in results.items() if not ok]
        number = alerts.notify(INCIDENT, 'Public health checks failed after three attempts at '
            + at + '.\n\nEndpoints: ' + ', '.join(failures)
            + '.\n\nNo private application data, response bodies or credentials are included. '
            'The next successful probe will close this incident.')
        raise RuntimeError('availability incident recorded as issue ' + str(number))


if __name__ == '__main__':
    main()
