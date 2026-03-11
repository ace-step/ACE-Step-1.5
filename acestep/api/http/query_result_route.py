"""HTTP route for querying one or more generation task results."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, Header, Request

from acestep.api.http.query_result_service import collect_query_results, parse_task_id_list


def register_query_result_route(
    app: FastAPI,
    verify_token_from_request: Callable[[dict, Optional[str]], Optional[str]],
    wrap_response: Callable[..., Dict[str, Any]],
    store: Any,
    map_status: Callable[[str], int],
    result_key_prefix: str,
    task_timeout_seconds: int,
    log_buffer: Any,
) -> None:
    """Register the ``/query_result`` endpoint.

    Args:
        app: FastAPI app instance to register the route on.
        verify_token_from_request: Auth validator used by legacy route.
        wrap_response: Response envelope builder preserving client contract.
        store: In-memory job store with ``get(task_id)``.
        map_status: Mapper from store status text to integer code.
        result_key_prefix: Prefix used for local-cache lookup keys.
        task_timeout_seconds: Timeout threshold for running cached jobs.
        log_buffer: Shared log buffer with ``last_message`` field.
    """

    @app.post("/query_result")
    async def query_result_endpoint(request: Request, authorization: Optional[str] = Header(None)):
        """Batch query result payloads for one or more task IDs.

        Args:
            request: HTTP request containing JSON or form fields.
            authorization: Optional Authorization header value.

        Returns:
            Wrapped payload list with one result item per task ID.
        """

        content_type = (request.headers.get("content-type") or "").lower()
        if "json" in content_type:
            body = await request.json()
        else:
            form = await request.form()
            body = {key: value for key, value in form.items()}

        verify_token_from_request(body, authorization)
        task_ids = parse_task_id_list(body.get("task_id_list", "[]"))
        local_cache = getattr(app.state, "local_cache", None)
        data_list = collect_query_results(
            task_ids=task_ids,
            local_cache=local_cache,
            store=store,
            map_status=map_status,
            result_key_prefix=result_key_prefix,
            task_timeout_seconds=task_timeout_seconds,
            get_log_last_message=lambda: log_buffer.last_message,
        )
        return wrap_response(data_list)
