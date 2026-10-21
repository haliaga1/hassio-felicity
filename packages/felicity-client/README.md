# felicity-client

Async Python client for the **Felicity Solar FSolar (Shine) cloud API**.

The FSolar API is **not public and not documented** by the vendor. This client
talks to the same endpoints the official web app uses, and is designed to
degrade gracefully when the vendor changes the contract.

> This package is not endorsed by, affiliated with, or supported by
> Felicity Solar.

## Install

```bash
pip install felicity-client
```

## Usage

```python
import asyncio

from felicity_client import FelicityClient, FileTokenStore


async def main() -> None:
    store = FileTokenStore("~/.config/felicity/tokens.json")
    async with FelicityClient("me@example.com", "hunter2", token_store=store) as client:
        plants = await client.list_plants()
        for plant in plants:
            print(plant.id, plant.name)

        devices = await client.list_devices(plant_id=plants[0].id)
        for device in devices:
            snapshot = await client.get_snapshot(device.serial_number)
            print(device.serial_number, snapshot.battery.soc, snapshot.pv.power)


asyncio.run(main())
```

### Real-time updates

```python
async for snapshot in client.realtime.stream_device(device_sn, collector_sn):
    print(snapshot.pv.power)
```

## What it covers

| Area | Endpoints |
|---|---|
| Authentication | `/userlogin` (RSA-encrypted password, bearer token) |
| Plants | `/plant/list_plant`, `/plant/plantDetails` |
| Devices | `/device/list_device_all_type`, `/device/get_device_snapshot` |
| Energy flow | `/device/get_energy_flow2` |
| Alerts | `/device/device_warring_list`, `/device/warring/group` |
| Real time | `wss://…/energy-flow/{deviceSn}` |

## Design notes

- **A missing value is `None`, never `0.0`.** The backend returns every number
  as a string and may return `null`. A fabricated zero is indistinguishable
  from a stopped inverter and corrupts Home Assistant statistics.
- **The gateway signals an expired token with a `302` to
  `/token_expiration`**, not with a `401`. The client disables redirects and
  translates that response into a token refresh.
- **TLS verification is always on.** If the vendor's certificate chain breaks
  again, the fix is to ship the missing intermediate, never to disable
  verification.
- **The public RSA key is embedded** and re-extracted live from the web app
  only if the backend rejects the ciphertext.

## Development

```bash
uv sync --all-packages --all-extras
make check
```

## License

MIT
