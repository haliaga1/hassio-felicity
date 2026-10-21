# Felicity Solar for Home Assistant

Exposes the metrics of a **Felicity Solar** installation (inverters, lithium
batteries and controllers) in Home Assistant, through the official FSolar
cloud — the same API the web app uses.

> **Not endorsed by, affiliated with, or supported by Felicity Solar.**
> The FSolar API is not public and not documented; see the limitations below.

## Why not just use Modbus?

The existing Modbus based integrations need a **wired RS485 connection**
between the inverter and Home Assistant. This integration talks to the cloud
the equipment is already connected to, so it works with the WiFi dongle
without touching the installation.

## Features

- **UI configuration** — email, password and the plant, no YAML.
- **Real time** — a WebSocket push stream, with REST polling as a fallback.
- **Plant aware** — the plant is chosen in the config flow, and its devices
  are grouped under a virtual "plant" device.
- **Energy Dashboard ready** — the lifetime counters are declared as
  `total_increasing`, the daily ones as `total` with a `last_reset`.
- **Alarms** — the active warnings of each device, with their details.
- **Bilingual** — English and Spanish.

## Installation

### HACS (recommended)

1. Open HACS → the three dots → **Custom repositories**.
2. Add `https://github.com/hugoaliaga/felicity-metrics`, category
   **Integration**.
3. Search for **Felicity Solar**, download it, then restart Home Assistant.

### Manual

Copy `custom_components/felicity_solar` into your Home Assistant
`config/custom_components/` folder and restart.

## Configuration

**Settings → Devices & Services → Add Integration → Felicity Solar**

1. Enter the email and password you use on the FSolar web app
   (`shine.felicitysolar.com`).
2. Pick the plant to expose. If the account has a single installation, the
   step is skipped.

Everything else is automatic: the devices of the plant are discovered and
each one becomes a Home Assistant device.

### Options

| Option | Default | What it does |
|---|---|---|
| Refresh interval | 60 s | How often the data is refreshed over REST. |
| Polling interval | 60 s | How often the data is refreshed while the WebSocket is down. |
| Use the WebSocket | on | Real-time push instead of polling. |
| Plant energy flow | on | Adds the plant level power sensors. |
| Warnings | on | Adds the alarm binary sensors. |

## Entities

Every Felicity device becomes a Home Assistant device with its own sensors.
The full mapping is in [`docs/entity-map.md`](../../docs/entity-map.md).

A few examples:

```yaml
# The inverter
sensor.casa_principal_inversor_principal_pv_power          # W
sensor.casa_principal_inversor_principal_pv_energy_total    # kWh, total_increasing
sensor.casa_principal_inversor_principal_grid_power         # W

# The battery
sensor.casa_principal_bateria_1_battery_state_of_charge     # %
sensor.casa_principal_bateria_1_battery_state_of_health      # %
sensor.casa_principal_bateria_1_battery_power               # W

# The plant
sensor.casa_principal_plant_pv_power                        # W
sensor.casa_principal_plant_grid_power                      # W
```

## Energy Dashboard

The production counter is ready as is:

| Panel | Sensor |
|---|---|
| Solar — production | `sensor.<plant>_<inverter>_pv_energy_total` |

The battery and the grid are **instantaneous** power sensors, so they need a
`utility_meter` to become counters. This is a native Home Assistant
component:

```yaml
utility_meter:
  - name: "Casa Principal - Solar"
    source: sensor.casa_principal_inversor_principal_pv_power
    unit_of_measurement: kWh
    device_class: energy
    state_class: total_increasing
    direction: import

  - name: "Casa Principal - Batería"
    source: sensor.casa_principal_bateria_1_battery_power
    unit_of_measurement: kWh
    device_class: energy
    state_class: total_increasing
    direction: import
```

> The sign of the power sensors follows the vendor's convention, which is
> **not documented**. The plant sensors expose a `sign_verified: false`
> attribute to say so. Check the sign against a known situation before
> wiring a `utility_meter` to them.

## Known limitations

- **The FSolar API is unofficial.** Felicity can change it without notice.
  The integration degrades to `unavailable` instead of breaking Home
  Assistant, and the client has a contract test suite against recorded
  payloads to catch a change early.
- **Import and export of grid energy are not counters.** The cloud does not
  expose them; only instantaneous flows. See the Energy Dashboard section.
- **The WebSocket may not accept a token without a browser session.** Until
  that is confirmed, the REST polling is the guaranteed path.
- **Write operations are not implemented.** The API supports changing the
  work mode and the setpoints, but v1 is strictly read-only.

## Development

```bash
uv venv --python 3.13 packages/homeassistant/.venv
VIRTUAL_ENV=packages/homeassistant/.venv uv pip install \
  "pytest-homeassistant-custom-component==0.13.316" homeassistant \
  -e packages/felicity-client
cd packages/homeassistant && .venv/bin/python -m pytest tests/ -q
```

## License

MIT
