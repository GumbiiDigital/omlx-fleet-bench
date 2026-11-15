"""oMLX admin API client (stdlib HTTP, cookie session)."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener

from bench.matrix import SETTING_FIELDS

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 10
ACTIVE_STATUSES = frozenset({"running", "pending", "started"})
TERMINAL_STREAM_TYPES = frozenset({"upload_done", "upload_skipped", "error"})


def load_api_key(settings_path: str) -> str:
    """Read auth.api_key from oMLX settings.json."""
    with open(settings_path, encoding="utf-8") as fh:
        data = json.load(fh)
    auth = data.get("auth") or {}
    key = auth.get("api_key")
    if not key or not isinstance(key, str):
        raise ValueError(f"Missing auth.api_key in {settings_path}")
    return key


def _json_request(
    opener: Any,
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    with opener.open(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        if not raw.strip():
            return None
        return json.loads(raw)


def cookie_opener() -> Any:
    """Opener that keeps the admin session cookie between calls."""
    return build_opener(HTTPCookieProcessor(CookieJar()))


class OMLXClient:
    """Session client for oMLX admin benchmark API."""

    def __init__(self, base_url: str, api_key: str, opener_factory: Callable[[], Any] = cookie_opener) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._opener_factory = opener_factory
        self._opener = opener_factory()

    def login(self) -> None:
        """Establish cookie session."""
        url = f"{self.base_url}/admin/api/login"
        body = {"api_key": self._api_key, "remember": False}
        _json_request(self._opener, "POST", url, body)
        logger.info("Logged in to oMLX admin API")

    def _request_with_relogin(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            return _json_request(self._opener, method, url, body)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Request failed (%s), re-login: %s", path, exc)
            self.login()
            return _json_request(self._opener, method, url, body)

    def list_models(self) -> List[Dict[str, Any]]:
        """GET /admin/api/models."""
        data = self._request_with_relogin("GET", "/admin/api/models")
        if isinstance(data, dict) and "models" in data:
            return list(data["models"])
        if isinstance(data, list):
            return data
        return []

    def get_model_settings(self, model: str) -> Dict[str, Any]:
        """Find one model's settings dict from the models list."""
        for entry in self.list_models():
            mid = entry.get("id") or entry.get("model_id") or entry.get("name")
            if mid == model:
                settings = entry.get("settings")
                if isinstance(settings, dict):
                    return dict(settings)
                return {k: v for k, v in entry.items() if k in SETTING_FIELDS}
        return {}

    def put_model_settings(self, model: str, settings: Dict[str, Any]) -> None:
        """PUT /admin/api/models/{model}/settings."""
        self._request_with_relogin(
            "PUT",
            f"/admin/api/models/{model}/settings",
            settings,
        )

    def start_benchmark(
        self,
        model_id: str,
        prompt_length: int,
        *,
        align_prompt_to_ane: bool = True,
    ) -> str:
        """POST /admin/api/bench/start; returns bench_id."""
        if not align_prompt_to_ane:
            raise ValueError("align_prompt_to_ane must be true for private runs")
        body = {
            "model_id": model_id,
            "context_profile": "code_python",
            "align_prompt_to_ane": True,
            "prompt_lengths": [prompt_length],
            "generation_length": 128,
            "batch_sizes": [],
            "force_lm_engine": False,
            "external": None,
        }
        data = self._request_with_relogin("POST", "/admin/api/bench/start", body)
        if not isinstance(data, dict) or "bench_id" not in data:
            raise RuntimeError(f"Unexpected bench start response: {data!r}")
        return str(data["bench_id"])

    def poll_results(self, bench_id: str) -> Dict[str, Any]:
        """GET /admin/api/bench/{id}/results until not active."""
        path = f"/admin/api/bench/{bench_id}/results"
        while True:
            try:
                data = self._request_with_relogin("GET", path)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                logger.warning("Poll error for %s, re-login", bench_id)
                self.login()
                data = self._request_with_relogin("GET", path)
            if not isinstance(data, dict):
                raise RuntimeError(f"Invalid poll payload: {data!r}")
            status = str(data.get("status", "")).lower()
            if status not in ACTIVE_STATUSES:
                return data
            time.sleep(POLL_INTERVAL_S)

    def read_stream_terminal_event(self, bench_id: str) -> Dict[str, Any]:
        """Read SSE stream until upload_done, upload_skipped, or error."""
        url = f"{self.base_url}/admin/api/bench/{bench_id}/stream"
        req = Request(url, headers={"Accept": "text/event-stream"}, method="GET")
        event: Dict[str, Any] = {}
        try:
            with self._opener.open(req, timeout=300) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload:
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type") or event.get("event")
                    if etype in TERMINAL_STREAM_TYPES:
                        return event
        except (HTTPError, URLError, TimeoutError):
            logger.warning("Stream error for %s, re-login and retry", bench_id)
            self.login()
            return self.read_stream_terminal_event(bench_id)
        return event

    @contextmanager
    def preserved_settings(self, model: str, fields: List[str]) -> Iterator[Dict[str, Any]]:
        """Snapshot `fields` once, yield, and restore only those fields in finally.

        The PUT schema forbids unknown keys, so only touched fields are ever sent.
        """
        original = self.get_model_settings(model)
        snapshot = {f: original.get(f) for f in fields}
        try:
            yield snapshot
        finally:
            try:
                self.put_model_settings(model, snapshot)
                logger.info("Restored %d settings for %s", len(snapshot), model)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                logger.error("Failed to restore settings for %s: %s", model, exc)

    def apply_settings(self, model: str, desired: Dict[str, Any], fields: List[str]) -> None:
        """PUT only the touched fields for one run."""
        self.put_model_settings(model, {f: desired.get(f) for f in fields})


def feature_keys(event: Dict[str, Any]) -> List[str]:
    """Extract feature flag keys from a stream/results event."""
    features = event.get("features") or []
    keys: List[str] = []
    for item in features:
        if isinstance(item, dict) and "key" in item:
            keys.append(str(item["key"]))
        elif isinstance(item, str):
            keys.append(item)
    return keys


def extract_result_metrics(results_payload: Dict[str, Any], prompt_length: int) -> Dict[str, Any]:
    """Pick the matching result row from the poll payload."""
    rows = results_payload.get("results") or results_payload.get("tests") or []
    if not isinstance(rows, list):
        rows = []
    chosen: Optional[Dict[str, Any]] = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        pp = row.get("pp")
        if pp is not None and int(pp) in (prompt_length, prompt_length + 1):
            chosen = row
            break
    if chosen is None and rows:
        chosen = rows[0] if isinstance(rows[0], dict) else None
    if chosen is None:
        return {}
    return {
        "pp": chosen.get("pp"),
        "ttft_ms": chosen.get("ttft_ms"),
        "processing_tps": chosen.get("processing_tps"),
        "gen_tps": chosen.get("gen_tps"),
        "tpot_ms": chosen.get("tpot_ms"),
        "e2e_latency_s": chosen.get("e2e_latency_s"),
        "peak_memory_bytes": chosen.get("peak_memory_bytes"),
    }