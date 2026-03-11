"""Unit tests for query-result route registration and helper behavior."""

import asyncio
import json
import time
import unittest
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute

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
    """Validate a fixed body/header token for route unit tests."""

    if (body or {}).get("ai_token") == "test-token":
        return
    if authorization == "Bearer test-token":
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def _map_status(status: str) -> int:
    """Map internal store status strings to legacy integer status values."""

    return {"queued": 0, "running": 0, "succeeded": 1, "failed": 2}.get(status, 2)


def _get_endpoint(app: FastAPI, path: str, method: str):
    """Return endpoint callable matching a route path/method pair."""

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method.upper() in route.methods:
            return route.endpoint
    raise AssertionError(f"Missing route: {method} {path}")


class _FakeStore:
    """Minimal in-memory store fake keyed by task ID."""

    def __init__(self, records: dict[str, object]) -> None:
        """Store deterministic records for ``get`` lookups."""

        self._records = records

    def get(self, task_id: str):
        """Return configured record by ID, or ``None`` when missing."""

        return self._records.get(task_id)


class QueryResultRouteTests(unittest.TestCase):
    """Behavior tests for query-result route decomposition."""

    def _build_app(self, records: dict[str, object] | None = None, local_cache: object | None = None) -> FastAPI:
        """Create app state and register query-result route for tests."""

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
            log_buffer=SimpleNamespace(last_message="working"),
        )
        return app

    def test_query_result_uses_cache_payload_when_present(self):
        """Route should return cache payload and running progress text when cache has fresh record."""

        create_time = int(time.time())
        cached = json.dumps([{"status": 0, "create_time": create_time}])
        local_cache = {"ace_step_v1.5_task-1": cached}
        app = self._build_app(local_cache=local_cache)
        endpoint = _get_endpoint(app, "/query_result", "POST")

        async def _json():
            """Return valid request body for cache-hit path test."""

            return {"ai_token": "test-token", "task_id_list": ["task-1"]}

        request = SimpleNamespace(headers={"content-type": "application/json"}, json=_json)
        result = asyncio.run(endpoint(request, None))
        self.assertEqual(200, result["code"])
        self.assertEqual(0, result["data"][0]["status"])
        self.assertEqual("working", result["data"][0]["progress_text"])

    def test_query_result_uses_store_payload_when_cache_missing(self):
        """Route should serialize store record payload when cache miss occurs."""

        record = SimpleNamespace(
            status="succeeded",
            created_at=123.0,
            result={
                "audio_paths": ["a.mp3"],
                "metas": {"caption": "c", "lyrics": "l", "bpm": 120},
            },
            progress_text="done",
            progress=1.0,
            stage="succeeded",
            error=None,
            env="development",
        )
        app = self._build_app(records={"task-2": record})
        endpoint = _get_endpoint(app, "/query_result", "POST")

        async def _json():
            """Return valid request body for store-fallback path test."""

            return {"ai_token": "test-token", "task_id_list": json.dumps(["task-2"])}

        request = SimpleNamespace(headers={"content-type": "application/json"}, json=_json)
        result = asyncio.run(endpoint(request, None))
        payload = result["data"][0]
        self.assertEqual(1, payload["status"])
        serialized = json.loads(payload["result"])
        self.assertEqual("a.mp3", serialized[0]["file"])
        self.assertEqual("c", serialized[0]["prompt"])

    def test_query_result_returns_empty_when_task_missing(self):
        """Route should preserve legacy missing-task response contract."""

        app = self._build_app()
        endpoint = _get_endpoint(app, "/query_result", "POST")

        async def _json():
            """Return valid request body for missing-task path test."""

            return {"ai_token": "test-token", "task_id_list": ["unknown-id"]}

        request = SimpleNamespace(headers={"content-type": "application/json"}, json=_json)
        result = asyncio.run(endpoint(request, None))
        self.assertEqual("[]", result["data"][0]["result"])
        self.assertEqual(0, result["data"][0]["status"])

    def test_query_result_falls_back_when_cache_json_is_non_list(self):
        """Route should treat non-list cache JSON payloads as failed cache entries."""

        local_cache = {"ace_step_v1.5_task-3": json.dumps({"status": 0, "create_time": int(time.time())})}
        app = self._build_app(local_cache=local_cache)
        endpoint = _get_endpoint(app, "/query_result", "POST")

        async def _json():
            """Return valid request body for malformed cache shape test."""

            return {"ai_token": "test-token", "task_id_list": ["task-3"]}

        request = SimpleNamespace(headers={"content-type": "application/json"}, json=_json)
        result = asyncio.run(endpoint(request, None))
        payload = result["data"][0]
        self.assertEqual(2, payload["status"])
        self.assertEqual(local_cache["ace_step_v1.5_task-3"], payload["result"])


if __name__ == "__main__":
    unittest.main()
