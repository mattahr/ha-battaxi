<p align="center">
  <img src="docs/logo.webp" alt="Stavsnäs Båttaxi" width="300">
</p>

# Stavsnäs Båttaxi for Home Assistant

A read-only [Home Assistant](https://www.home-assistant.io/) custom integration
that shows upcoming [Stavsnäs Båttaxi](https://www.battaxi.se/) departures for
a route you pick in the UI, for example **Stavsnäs → Telegrafholmen** on
Sandhamnslinjen.

Lines and piers are fetched live from Båttaxi's booking API, so nothing is
hard-coded and no API key or YAML is needed. Booking is out of scope.

> **Note:** Båttaxi's API is undocumented and may change without notice. The
> integration validates every response and fails gracefully, but it is not an
> official product of Stavsnäs Båttaxi.

## Installation

### HACS (recommended)

1. In HACS, open **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/mattahr/ha-battaxi` with category **Integration**.
3. Install **Stavsnäs Båttaxi** and restart Home Assistant.

### Manual

Copy `custom_components/stavsnas_battaxi` into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Configuration

**Settings → Devices & services → Add integration → Stavsnäs Båttaxi**

The flow has three steps, all populated from the API:

1. **Line** – e.g. Sandhamnslinjen.
2. **From pier** – any pier the line boards at.
3. **To pier** – only piers the boat actually reaches *after* the pier you
   chose, following the line's real stop order (return legs included).

Each route becomes one config entry and one device named
`<from> → <to>` (manufacturer *Stavsnäs Båttaxi*, model = line name). Add the
integration again for more routes, e.g. the opposite direction. A route can be
changed later with **Reconfigure** on the entry.

## Entities

| Entity | Type | Value |
|---|---|---|
| `sensor.<route>_next_departure` | timestamp | Next departure that has not left yet, e.g. `2026-09-12T19:10:00+02:00`. Attributes: `line`, `origin`, `destination`, `departure_id`. |
| `sensor.<route>_next_arrival` | timestamp | Arrival time of that departure. |
| `sensor.<route>_available_seats` | number | Seats left on that departure (`unknown` if the API does not say). |
| `binary_sensor.<route>_bookable` | on/off | Whether Båttaxi currently offers booking for it. **`off` does not mean cancelled** – it can be full, too close to departure, etc. |
| `sensor.<route>_departures_today` | number | Remaining departures today. Attribute `departures`: list of `{departure, arrival, available_seats, bookable}`. |
| `sensor.<route>_next_departure_text` | text | `19:10 Stavsnäs → 19:45 Telegrafholmen · 58 lediga` (`· ej bokningsbar` when not bookable, `13/9 ` prefix when the next departure is another day). |
| `sensor.<route>_departures_today_text` | text | `15:10 – 12 platser \| 17:10 \| 19:40 – 47 platser`, or `Inga fler avgångar idag`. |

The timestamp/number sensors are the source of truth for automations; the
text sensors are convenience strings for dashboards.

### Automation example

```yaml
automation:
  - alias: "Remind me 30 minutes before the boat"
    triggers:
      - trigger: template
        value_template: >
          {{ states('sensor.stavsnas_telegrafholmen_next_departure') not in ['unknown', 'unavailable']
             and (as_timestamp(states('sensor.stavsnas_telegrafholmen_next_departure')) - as_timestamp(now())) < 1800 }}
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "{{ states('sensor.stavsnas_telegrafholmen_next_departure_text') }}"
```

## How data is fetched

- Departures come from `GET /api/search?origin&dest&date`; piers and lines
  from `/api/public/piers` and `/api/public/lines` (only during setup).
- Today's departures are polled every **5 minutes**; departures that already
  left are filtered out locally.
- When nothing is left today, the integration looks ahead **up to 14 days** to
  find the next departure. Future days are cached for **6 hours** (empty days
  too), so steady-state polling is normally one request per 5 minutes.
- Times from the API are interpreted in `Europe/Stockholm`.
- API errors (timeouts, HTTP 429/5xx, malformed JSON) mark the entities
  unavailable until the next successful poll; nothing is retried aggressively.

Diagnostics (**⋮ → Download diagnostics** on the entry) include the route, the
last update and the cached dates.

## Development

Requirements: Python ≥ 3.14, [uv](https://docs.astral.sh/uv/), Docker (for the
live Home Assistant).

```bash
uv sync --group dev        # creates .venv with Home Assistant + test tooling
uv run pytest              # unit + integration tests (no network needed)
uv run ruff check . && uv run ruff format .
```

### Run it in a real Home Assistant with F5

`docker-compose.yml` starts `ghcr.io/home-assistant/home-assistant:stable`
with `custom_components/` mounted into the container and
[debugpy](https://www.home-assistant.io/integrations/debugpy/) enabled.

1. Open the folder in VS Code (install the recommended extensions).
2. Press **F5** (*Home Assistant (Docker): attach*). The pre-launch task
   `ha: up` starts the container and waits until debugpy answers; then the
   debugger attaches, so breakpoints in `custom_components/` hit.
3. Open http://localhost:8123, finish onboarding, then **Add integration →
   Stavsnäs Båttaxi**.
4. After editing code, run the task **ha: restart** (Home Assistant needs a
   restart to reload a custom integration) and press F5 again.

`ha: up` refuses to start if port 8123 or 5678 is already used by something
else (for example another Home Assistant dev container) and tells you which
container or process holds it. To run side by side, copy `.env.example` to
`.env` and set `HA_PORT`/`DEBUGPY_PORT` (if you change `DEBUGPY_PORT`, update
`.vscode/launch.json` too).

Other tasks: `ha: down`, `ha: logs`, `ha: status`, or run `dev/ha.sh` directly.
The container's state lives in `dev/config/` (git-ignored except
`configuration.yaml`).

### Project layout

```
custom_components/stavsnas_battaxi/
  api.py           API client + JSON → dataclasses (schema validation lives here)
  routes.py        valid directed routes from a line's ordered stop list
  coordinator.py   polling, per-date cache, next-departure selection
  config_flow.py   line → from pier → to pier (also used for reconfigure)
  sensor.py, binary_sensor.py, entity.py, formatting.py, diagnostics.py
tests/             pytest-homeassistant-custom-component tests + API fixtures
docs/              design spec (Swedish) and implementation plan
```

## License

MIT – see [LICENSE](LICENSE).
