"""API client for the classic Flo API (shutoff valve + leak detector pucks).

This talks to a different backend than the NAB/sump-pump API in api.py:
  - Auth:    https://api.prod.iot.moen.com/v1/oauth2/token
  - Devices: https://api-gw.meetflo.com/api/v2/locations/{id}?expand=devices
  - Control: https://api-gw.meetflo.com/api/v2/devices/{id}

Both APIs share the same Cognito app client_id, so a single Moen account
login authenticates against both, which is what lets this integration
surface the sump pump, the shutoff valve, and leak detector pucks under
one config entry.

IMPORTANT: both of the above hosts negotiate ALPN "h2" (HTTP/2) with the
real iOS app, and appear to reject/misbehave (observed: bare "501 Not
Implemented") on plain HTTP/1.1 requests -- so this client uses `httpx`
with HTTP/2 support explicitly enabled, rather than the aiohttp session
used elsewhere in this integration (aiohttp is HTTP/1.1-only).

Reverse-engineered via mitmproxy capture of the iOS Moen Smart Water
Network app (Smartwater-iOS-prod-3.57.0), July 2026.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from .const import CLIENT_ID, FLO_API_BASE, FLO_AUTH_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class FloClassicApiError(Exception):
    """Base exception for classic Flo API errors."""


class FloClassicAuthError(FloClassicApiError):
    """Authentication error."""


class MoenFloClassicClient:
    """Client for the classic Flo API (shutoff valve + leak detector pucks)."""

    # Fallback used only when no location_id was configured (e.g. an
    # existing config entry created before this became configurable).
    # New installs should supply their own via the config flow -- see
    # README for how to find yours via mitmproxy.
    _FALLBACK_LOCATION_ID = "26fc8c76-ca4b-4bcc-ad54-ca02a2479305"

    def __init__(
        self, username: str, password: str, location_id: Optional[str] = None
    ) -> None:
        self.username = username
        self.password = password
        self._configured_location_id = location_id or None
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._user_id: Optional[str] = None
        self._location_ids: List[str] = []
        self._location_timezone: str = "America/New_York"

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily construct the httpx client off the event loop.

        httpx.AsyncClient(http2=True) reads SSL certs from disk at
        construction time, which HA's event loop flags as a blocking call
        if done directly on the loop -- so we build it via an executor on
        first use instead.
        """
        if self._client is None:
            import asyncio

            loop = asyncio.get_event_loop()
            self._client = await loop.run_in_executor(
                None, lambda: httpx.AsyncClient(http2=True, timeout=30.0)
            )
        return self._client

    async def async_close(self) -> None:
        """Close the underlying HTTP client. Call on integration unload."""
        if self._client is not None:
            await self._client.aclose()

    async def authenticate(self) -> None:
        """Authenticate against the classic Flo API.

        NOTE: the real app's initial login request does NOT include a
        "grant_type" field at all -- that field only appears on the
        *refresh* call ("grant_type":"refresh_token"). Including
        "grant_type":"password" here (a reasonable-looking but incorrect
        assumption) caused the backend to return a bare 501 "Not
        Implemented" for every login attempt, regardless of HTTP client,
        HTTP/2 support, or TLS fingerprint -- confirmed via mitmproxy
        capture comparison, July 2026.
        """
        payload = {
            "client_id": CLIENT_ID,
            "username": self.username,
            "password": self.password,
        }
        await self._token_request(payload)

    async def _refresh(self) -> None:
        """Refresh the access token using the stored refresh token."""
        if not self._refresh_token:
            await self.authenticate()
            return

        payload = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": self._refresh_token,
        }
        try:
            await self._token_request(payload)
        except FloClassicApiError:
            _LOGGER.info("Flo classic refresh_token expired, doing a fresh login")
            await self.authenticate()

    async def _token_request(self, payload: Dict[str, Any]) -> None:
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
        }
        client = await self._get_client()
        try:
            response = await client.post(
                FLO_AUTH_URL, content=json.dumps(payload), headers=headers
            )
            if response.status_code != 200:
                _LOGGER.warning(
                    "Flo classic auth failed. HTTP version=%s, status=%s, "
                    "response headers=%s, body=%s",
                    response.http_version,
                    response.status_code,
                    dict(response.headers),
                    response.text,
                )
                raise FloClassicAuthError(
                    f"Flo classic auth failed ({response.status_code}): {response.text}"
                )
            data = response.json()
            token = data.get("token", data)  # some grants nest under "token"
            self._access_token = token.get("access_token")
            self._refresh_token = token.get("refresh_token", self._refresh_token)
            id_token = token.get("id_token")
            expires_in = token.get("expires_in", 3600)
            # Refresh a bit early to be safe.
            self._token_expiry = datetime.now() + timedelta(seconds=expires_in - 300)
            if not self._access_token:
                raise FloClassicAuthError("No access_token in Flo classic auth response")
            if id_token:
                self._user_id = self._decode_jwt_sub(id_token)
            _LOGGER.info(
                "Authenticated with classic Flo API over HTTP/%s",
                response.http_version,
            )
        except httpx.HTTPError as err:
            raise FloClassicApiError(f"Network error during Flo classic auth: {err}") from err

    async def _ensure_authenticated(self) -> None:
        if not self._access_token or not self._token_expiry:
            await self.authenticate()
        elif datetime.now() >= self._token_expiry:
            await self._refresh()

    async def _headers(self) -> Dict[str, str]:
        await self._ensure_authenticated()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    @staticmethod
    def _decode_jwt_sub(id_token: str) -> Optional[str]:
        """Extract the 'sub' claim from a JWT without verifying it.

        Not currently load-bearing: location lookup uses the configured
        location_id instead (see async_get_user_locations), since none
        of this token's claims successfully resolve locations via
        /users/{claim}?expand=locations on this backend. Kept only in
        case a future endpoint discovery makes this claim useful again.
        """
        try:
            payload_b64 = id_token.split(".")[1]
            padding = "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
            return payload.get("sub") or payload.get("username")
        except (IndexError, ValueError, TypeError):
            _LOGGER.debug("Could not decode Flo classic id_token to find user id")
            return None

    async def async_get_user_locations(self) -> List[str]:
        """Return the location IDs tied to this account.

        NOTE: the "proper" discovery path (decode JWT -> GET
        /users/{id}?expand=locations) returns 403 with this backend --
        none of the JWT claims tried (sub, email, cognito:username) match
        whatever internal id this endpoint actually expects. As a
        pragmatic fix, this uses the location_id supplied via the config
        flow if present, falling back to a known-working default
        otherwise (for entries created before this was configurable).
        See README for how to find your own location_id via mitmproxy.
        """
        location_id = self._configured_location_id or self._FALLBACK_LOCATION_ID
        self._location_ids = [location_id]
        return self._location_ids

    async def async_get_location_devices(self, location_id: str) -> List[Dict[str, Any]]:
        """Return the raw device list for a location (shutoff valve + pucks)."""
        headers = await self._headers()
        url = f"{FLO_API_BASE}/locations/{location_id}?expand=devices"
        try:
            client = await self._get_client()
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as err:
            raise FloClassicApiError(f"Network error fetching Flo devices: {err}") from err
        if response.status_code != 200:
            raise FloClassicApiError(
                f"Failed to fetch Flo location devices ({response.status_code}): {response.text}"
            )
        data = response.json()
        if location_id not in self._location_ids:
            self._location_ids.append(location_id)
        self._location_timezone = data.get("timezone", "America/New_York")
        return data.get("devices", [])

    async def async_get_water_consumption_today(self, mac_address: str) -> Optional[float]:
        """Return total gallons consumed so far today for a device.

        Uses the location's timezone (captured during device discovery)
        to compute local midnight-to-now, matching what the Moen app
        shows as "today's usage".
        """
        try:
            from zoneinfo import ZoneInfo
        except ImportError:  # pragma: no cover - py<3.9 fallback, HA requires 3.13+
            ZoneInfo = None

        now = datetime.now(ZoneInfo(self._location_timezone)) if ZoneInfo else datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # end_date is exclusive-ish in the API's own examples (next day, 05:00 UTC
        # cutoff) -- mirror that pattern by asking through "now".
        start_date = start_of_day.strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        headers = await self._headers()
        url = (
            f"{FLO_API_BASE}/water/consumption"
            f"?macAddress={mac_address}&interval=1d"
            f"&startDate={start_date}&endDate={end_date}"
            f"&tz={self._location_timezone}"
        )
        try:
            client = await self._get_client()
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as err:
            _LOGGER.warning("Network error fetching water consumption: %s", err)
            return None
        if response.status_code != 200:
            _LOGGER.warning(
                "Failed to fetch water consumption (%s): %s",
                response.status_code,
                response.text,
            )
            return None
        data = response.json()
        return data.get("aggregations", {}).get("sumTotalGallonsConsumed")

    async def async_get_device(self, device_id: str) -> Dict[str, Any]:
        """Fetch a single device's current state."""
        headers = await self._headers()
        url = f"{FLO_API_BASE}/devices/{device_id}"
        try:
            client = await self._get_client()
            response = await client.get(url, headers=headers)
        except httpx.HTTPError as err:
            raise FloClassicApiError(f"Network error fetching Flo device: {err}") from err
        if response.status_code != 200:
            raise FloClassicApiError(
                f"Failed to fetch Flo device {device_id} ({response.status_code}): {response.text}"
            )
        return response.json()

    async def async_set_valve(self, device_id: str, target: str) -> None:
        """Open or close the shutoff valve. target is 'open' or 'closed'."""
        if target not in ("open", "closed"):
            raise ValueError("target must be 'open' or 'closed'")
        headers = await self._headers()
        url = f"{FLO_API_BASE}/devices/{device_id}"
        payload = {"valve": {"target": target}}
        try:
            client = await self._get_client()
            response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as err:
            raise FloClassicApiError(f"Network error setting valve: {err}") from err
        if response.status_code not in (200, 202, 204):
            raise FloClassicApiError(
                f"Failed to set valve on device {device_id} "
                f"({response.status_code}): {response.text}"
            )
        _LOGGER.info("Set valve target=%s on device %s", target, device_id)
