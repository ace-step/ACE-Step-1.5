"""HTTP integration tests for query-result route behavior."""

import json
import time
import unittest
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from acestep.api.http.query_result_route import register_query_result_route


def _wrap_response(data, code=200, error=None):
    """Return an ``api_server``-compatible response envelope dict."""

    return {
        "data": data,
        "code": code,
        "error": error,
        "timestamp": int(time.time() * 1000),
        "extra": None,
    }


def _verify_token_from_request(body: dict, authorization: str | None = None) -> None:
    """Validate a fixed body/header token for HTTP tests."""

    if (body or {}).get("ai_token") == "test-token":
        return
    if authorization == "Bearer test-token":
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def _map_status(status: str) -> int:
    """Map internal store status strings to legacy integer status values."""

    return {"queued": 0, "running": 0, "succeeded": 1, "failed": 2}.get(status, 2)


class _FakeStore:
    """Minimal in-memory store fake keyed by task ID."""

    def __init__(self, records: dict[str, object]) -> None:
        """Store deterministic records for ``get`` lookups."""

        self._records = records

    def get(self, task_id: str):
        """Return configured record by ID, or ``None`` when missing."""

        return self._records.get(task_id)


class QueryResultRouteHttpTests(unittest.TestCase):
    """Integration tests covering real HTTP calls for query-result route."""

    def _build_client(self, records: dict[str, object] | None = None, local_cache: object | None = None) -> TestClient:
        """Create app and register query-result route for HTTP tests."""

        app = FastAPI()
        app.state.local_cache = local_cache
        register_query_result_route(
            app=app,
            verify_token_from_request=_verify_token_from_request,
            wrap_response=_wrap_response,
            store=_FakeStore(records or {}),
            map_status=_map_status,
            result_key_prefix="ace_step_v1.5_",
            task_timeout_seconds=3600,
            log_buffer=SimpleNamespace(last_message="processing"),
        )
        return TestClient(app)

    def test_query_result_requires_auth(self):
        """POST /query_result should return 401 when auth token is missing."""

        client = self._build_client()
        response = client.post("/query_result", json={"task_id_list": ["task-1"]})
        self.assertEqual(401, response.status_code)

    def test_query_result_marks_timed_out_cache_entry_as_failed(self):
        """POST /query_result should return status 2 for stale running cache entries."""

        stale = json.dumps([{"status": 0, "create_time": int(time.time()) - 7200}])
        local_cache = {"ace_step_v1.5_task-1": stale}
        client = self._build_client(local_cache=local_cache)
        response = client.post("/query_result", json={"ai_token": "test-token", "task_id_list": ["task-1"]})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        self.assertEqual(2, payload["data"][0]["status"])
        self.assertIn("timestamp", payload)
        self.assertIsNone(payload["extra"])

    def test_query_result_returns_full_analysis_result_directly(self):
        """POST /query_result should preserve full-analysis payload wrapping contract."""

        record = SimpleNamespace(
            status="succeeded",
            created_at=100.0,
            result={"status_message": "Full Hardware Analysis Success", "analysis": "ok"},
            progress_text="done",
            progress=1.0,
            stage="succeeded",
            error=None,
            env="development",
        )
        client = self._build_client(records={"task-3": record})
        response = client.post("/query_result", json={"ai_token": "test-token", "task_id_list": ["task-3"]})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        result_json = json.loads(payload["data"][0]["result"])
        self.assertEqual("Full Hardware Analysis Success", result_json[0]["status_message"])

    def test_query_result_accepts_form_encoded_payload(self):
        """POST /query_result should accept form payloads and parse task IDs from JSON text."""

        record = SimpleNamespace(
            status="succeeded",
            created_at=100.0,
            result={"audio_paths": ["form.mp3"], "metas": {"caption": "c"}},
            progress_text="done",
            progress=1.0,
            stage="succeeded",
            error=None,
            env="development",
        )
        client = self._build_client(records={"task-form": record})
        response = client.post(
            "/query_result",
            data={"ai_token": "test-token", "task_id_list": json.dumps(["task-form"])},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(200, payload["code"])
        result_json = json.loads(payload["data"][0]["result"])
        self.assertEqual("form.mp3", result_json[0]["file"])

    def test_query_result_returns_empty_data_for_missing_task_id_list(self):
        """POST /query_result should return an empty result list when task IDs are omitted."""

        client = self._build_client()
        response = client.post("/query_result", json={"ai_token": "test-token"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual([], payload["data"])

    def test_query_result_returns_empty_data_for_malformed_task_id_list(self):
        """POST /query_result should return an empty result list when task IDs are malformed."""

        client = self._build_client()
        response = client.post(
            "/query_result",
            json={"ai_token": "test-token", "task_id_list": "not-valid-json"},
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual([], payload["data"])

    def test_query_result_preserves_non_list_json_task_id_iteration(self):
        """POST /query_result should keep legacy iteration behavior for parsed non-list JSON payloads."""

        client = self._build_client()
        response = client.post(
            "/query_result",
            json={"ai_token": "test-token", "task_id_list": '{"task-a": 1, "task-b": 2}'},
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(2, len(payload["data"]))
        self.assertEqual("task-a", payload["data"][0]["task_id"])
        self.assertEqual("task-b", payload["data"][1]["task_id"])
        self.assertEqual(0, payload["data"][0]["status"])
        self.assertEqual(0, payload["data"][1]["status"])


if __name__ == "__main__":
    unittest.main()
