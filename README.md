# Moen Smart Water for Home Assistant — Sump Pump + Shutoff Valve + Leak Detectors

A single Home Assistant integration, one Moen account login, covering:

- **Moen Smart Sump Pump Monitor** (model S2000ESUSA)
- **Flo Smart Water Shutoff Valve** (open/close control, flow rate, pressure, water temperature)
- **Flo Smart Leak Detector pucks** (water detection, humidity, temperature, battery)

## Why this exists

Moen's ecosystem is split across two backends under the hood:

1. A newer AWS Cognito + Lambda-"invoker" API (`smartwater-app-*`) used by the sump pump monitor.
2. An older but still-functional REST API (`api-gw.meetflo.com/v2`) used by the shutoff valve and leak detector pucks, authenticated through a **different, newer** OAuth2 endpoint (`api.prod.iot.moen.com`) than any existing Home Assistant integration was pointed at.

Both backends share the same Cognito app client ID, so **one username/password login authenticates against both** — this integration takes advantage of that to surface every device family under a single config entry.

## Origins & credit

Forked from [`patrickjcash/ha-moen-flo`](https://github.com/patrickjcash/ha-moen-flo) (MIT licensed), which implemented the sump pump monitor support. This fork adds:

- `flo_classic_api.py` — API client for the shutoff valve + leak detector puck backend
- `valve.py` — new platform exposing the shutoff valve as a controllable `valve` entity
- Additional sensors/binary sensors for pucks (temperature, humidity, battery, water-detected) and the shutoff valve (flow rate, pressure, water temperature)
- A second, independent `DataUpdateCoordinator` for the classic Flo API, so a failure there never breaks sump pump support
- An optional config field for your Flo location ID (see **Setup notes** below — this is currently required for shutoff valve/puck support to work on accounts other than the one this was built against)

All reverse-engineered via `mitmproxy` capture of the iOS Moen Smart Water Network app (`Smartwater-iOS-prod-3.57.0`) and confirmed with direct `curl`/Python testing, July 2026.

## Installation (HACS)

1. HACS → Custom repositories → add this repo URL, category **Integration**
2. Search HACS for "Moen Smart Water" → Download
3. Restart Home Assistant
4. Settings → Devices & Services → Add Integration → search "Moen" → enter your Moen account email/password, and optionally your Flo location ID (see below)

## Setup notes: finding your Flo location ID

Automatic location discovery (decoding your login token to look up your account's locations) does **not** work against this backend — every JWT claim we tried (`sub`, `email`, `cognito:username`) returns a `403 Forbidden` from the `/users/{id}?expand=locations` endpoint. The actual internal ID this endpoint expects hasn't been identified yet (if you figure it out, please open a PR).

**If you only have a sump pump monitor:** leave the location ID field blank — it's not needed.

**If you have a shutoff valve or leak detector pucks:** you'll need to find your location ID once, via the same `mitmproxy` method used to build this integration:

1. Set up `mitmproxy` as a proxy for your phone (see [mitmproxy docs](https://docs.mitmproxy.org/stable/overview-getting-started/) — install the CA cert on your phone, set it as your WiFi proxy)
2. Open the Moen Smart Water Network app on your phone, view your shutoff valve or a leak detector's status screen
3. In mitmproxy, find a request like `GET https://api-gw.meetflo.com/api/v2/locations/{location_id}?expand=devices`
4. Copy the `{location_id}` (a UUID) from that URL into the config flow's "Flo location ID" field

This is genuinely inconvenient for a first-time setup, and improving this is the single highest-value contribution this repo could use.

## What you'll see

**Sump Pump Monitor** — unchanged from upstream: water level, temperature, humidity, pump cycle history, alerts, battery/WiFi diagnostics.

**Shutoff Valve** — a `valve` entity (open/close), plus sensors for flow rate (gal/min), pressure (psi), and water temperature.

**Leak Detector Pucks** (one device per puck) — temperature, humidity, and battery sensors, plus binary sensors for water-detected and low-battery.

**Not yet included:** water consumption/usage history (daily/weekly totals). The Moen app has this, but it comes from a different endpoint that hasn't been captured/reverse-engineered yet.

## Known limitations

- No automatic location discovery (see above) — location ID must currently be found manually via mitmproxy for shutoff valve/puck support.
- Classic Flo API access tokens expire hourly and are refreshed automatically via the stored refresh token; a full re-login only happens if the refresh token itself has expired.
- This integration is unofficial, reverse-engineered, and not affiliated with or supported by Moen or Fortune Brands. It may break if Moen changes these APIs.
- Only tested against one real account so far (one sump pump, one shutoff valve, six leak detector pucks). Wider testing welcome via issues/PRs.
- No water consumption/usage history sensors yet (see above).

## Disclaimer

This is an **unofficial, community-developed integration**, provided "AS IS" without warranty of any kind. It is **not affiliated with, endorsed by, or supported by** Moen or Fortune Brands Home & Security, Inc. It may stop working at any time due to API changes on Moen's side. **Do not rely on this for safety-critical monitoring** (e.g., as your sole leak/flood detection) — always maintain a physical/professional backup for anything safety-relevant.

## License

MIT, same as upstream. See `LICENSE`.
