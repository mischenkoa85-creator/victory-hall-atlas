"""No network/SQL: checks the existing session and workspace scope boundary."""
from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).parents[1]))
import power_api as p
from bff.models import AuthenticationDenied, PermissionDenied, ServiceUnavailable
from bff.security import SESSION_COOKIE, ORIGIN

SECRET = 'f'*43
URL = '/v1/session/power/' + str(p.FACILITY_ID)
HEADERS = {'Cookie': SESSION_COOKIE+'='+SECRET}


class Repository:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.context = {'facility_id': str(p.FACILITY_ID), 'user_id': 'verified-user'}

    @contextmanager
    def _request(self, secret, csrf=None):
        assert secret == SECRET and csrf is None
        if self.failure:
            raise self.failure()
        yield self

    def execute(self, statement, params):
        self.calls.append((statement, params))
        return self

    def fetchone(self):
        return {'result': self.context}


@pytest.fixture
def client(monkeypatch):
    reader = Mock(return_value={'source': 'FRESH', 'grid': 'PRESENT'})
    monkeypatch.setattr(p, 'read_projection', reader)
    repo = Repository()
    app = FastAPI()
    p.attach_power(app, repo)
    with TestClient(app, base_url=ORIGIN) as c:
        yield c, repo, reader


def test_anonymous_denied_before_database_and_file(client):
    c, repo, reader = client
    result = c.get(URL)
    assert result.status_code == 401 and result.headers['cache-control'] == 'no-store'
    assert not repo.calls
    reader.assert_not_called()


def test_scoped_user_reads_flat_json_without_csrf(client):
    c, repo, reader = client
    result = c.get(URL, headers=HEADERS)
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert result.json() == {'source': 'FRESH', 'grid': 'PRESENT'}
    assert repo.calls == [('SELECT atlas_ops.workspace_context(%s) AS result', (p.FACILITY_ID,))]
    reader.assert_called_once_with()


@pytest.mark.parametrize('failure,status', [(AuthenticationDenied, 401), (PermissionDenied, 403), (ServiceUnavailable, 503)])
def test_current_session_and_scope_denial_before_file(client, failure, status):
    c, repo, reader = client
    repo.failure = failure
    result = c.get(URL, headers=HEADERS)
    assert result.status_code == status and result.headers['cache-control'] == 'no-store'
    reader.assert_not_called()


def test_other_facility_denied_without_sql_or_file(client):
    c, repo, reader = client
    result = c.get('/v1/session/power/00000000-0000-0000-0000-000000000001', headers=HEADERS)
    assert result.status_code == 403 and not repo.calls
    reader.assert_not_called()


def test_mismatched_database_context_does_not_read_file(client):
    c, repo, reader = client
    repo.context = {'facility_id': 'wrong'}
    assert c.get(URL, headers=HEADERS).status_code == 503
    reader.assert_not_called()


def test_missing_or_invalid_projection_is_generic_503(client):
    c, repo, reader = client
    reader.side_effect = p.ProjectionUnavailable()
    result = c.get(URL, headers=HEADERS)
    assert result.status_code == 503 and result.headers['cache-control'] == 'no-store'
    assert result.json() == {'code': 'POWER_UNAVAILABLE'}


def test_path_is_not_client_selectable_and_route_is_readonly(client):
    c, repo, reader = client
    assert c.get(URL+'?path=/raw-live-state&facility=other', headers=HEADERS).status_code == 200
    reader.assert_called_once_with()
    assert c.post(URL, headers=HEADERS).status_code == 405
