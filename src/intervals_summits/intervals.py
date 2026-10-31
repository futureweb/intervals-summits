"""A small Intervals.icu client: paced (the API key is usually shared with the Garmin bridge) and
patient with 429 – it waits as long as Intervals asks and tries again."""
from __future__ import annotations

import logging
import time
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import requests

from . import __version__

log = logging.getLogger(__name__)
ROOT = "https://intervals.icu/api/v1"
RETRIES = 6


def retry_after(response: requests.Response) -> float:
    value = response.headers.get("Retry-After")
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return 0.0


class IntervalsClient:
    def __init__(self, api_key: str, athlete_id: str = "0", *, pause: float = 0.6,
                 session: requests.Session | None = None, sleep: Callable[[float], None] = time.sleep):
        if not api_key:
            raise ValueError("INTERVALS_API_KEY required")
        self.athlete = athlete_id or "0"
        self.pause = pause
        self.sleep = sleep
        self.session = session or requests.Session()
        self.session.auth = ("API_KEY", api_key)
        self.session.headers["User-Agent"] = f"intervals-summits/{__version__}"
        self._last = 0.0
        self.requests = 0

    def _api(self, method: str, path: str, **kwargs) -> Any:
        for attempt in range(RETRIES):
            wait = self._last + self.pause - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            response = self.session.request(method, f"{ROOT}{path}", timeout=(10, 75), **kwargs)
            if response.status_code == 429 and attempt < RETRIES - 1:
                pause = min(600.0, retry_after(response) or 30.0 * (attempt + 1))
                log.info("Intervals asks to slow down (429); waiting %.0f s", pause)
                self.sleep(pause)
                continue
            if response.status_code in (502, 503, 504) and method == "GET" and attempt < 3:
                self.sleep(20.0 * (attempt + 1))
                continue
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        raise RuntimeError("unreachable")

    def _athlete(self, method: str, path: str, **kwargs) -> Any:
        return self._api(method, f"/athlete/{self.athlete}{path}", **kwargs)

    def activities(self, oldest: date, newest: date, fields: list[str] | None = None) -> list[dict]:
        params = {"oldest": oldest.isoformat(), "newest": newest.isoformat()}
        if fields:
            params["fields"] = ",".join(fields)
        result = self._athlete("GET", "/activities", params=params)
        if not isinstance(result, list):
            raise ValueError("Intervals activities API did not return a list")
        return result

    def streams(self, activity_id: str, types: list[str]) -> list[dict]:
        result = self._api("GET", f"/activity/{activity_id}/streams.json", params={"types": ",".join(types)})
        if not isinstance(result, list):
            raise ValueError("Intervals streams API did not return a list")
        return result

    def update_activity(self, activity_id: str, values: dict) -> Any:
        return self._api("PUT", f"/activity/{activity_id}", json=values)

    def custom_items(self) -> list[dict]:
        result = self._athlete("GET", "/custom-item")
        if not isinstance(result, list):
            raise ValueError("Intervals custom items response was not a list")
        return result

    def create_custom_item(self, item: dict) -> Any:
        return self._athlete("POST", "/custom-item", json=item)

    def update_custom_item(self, item_id: int, item: dict) -> Any:
        return self._athlete("PUT", f"/custom-item/{int(item_id)}", json=item)

    def reorder_custom_items(self, items: list[dict]) -> Any:
        """A new item lands at index 0, where Intervals' pickers do not show it: give it the next index."""
        return self._athlete("PUT", "/custom-item-indexes", json=items)
