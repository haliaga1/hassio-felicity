"""Diagnostics support for the Felicity Solar integration.

The credentials and the bearer token are never included in the dump: a
diagnostic file ends up in a GitHub issue, and it must not leak the account.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_SERIALS,
    CONF_EMAIL,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    CONF_SCAN_DEVICES,
    DOMAIN,
)
from .coordinator import FelicityCoordinator


def _redact_email(email: str) -> str:
    """Redact an email address, keeping just enough to identify it."""
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    head = local[:1] if local else ""
    return f"{head}***@{domain}"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the diagnostics of a config entry."""
    coordinator: FelicityCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    data: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": {
                CONF_EMAIL: _redact_email(str(entry.data.get(CONF_EMAIL, ""))),
                CONF_PLANT_ID: entry.data.get(CONF_PLANT_ID),
                CONF_PLANT_NAME: entry.data.get(CONF_PLANT_NAME),
                CONF_SCAN_DEVICES: entry.data.get(CONF_SCAN_DEVICES),
                CONF_DEVICE_SERIALS: entry.data.get(CONF_DEVICE_SERIALS),
            },
            "options": dict(entry.options),
        }
    }

    if coordinator is None:
        return data

    current = coordinator.data
    data["coordinator"] = {
        "source": current.source if current else None,
        "device_count": len(current.devices) if current else 0,
        "snapshot_count": len(current.snapshots) if current else 0,
        "alert_count": len(current.alerts) if current else 0,
        "websocket_connected": coordinator._ws_connected,
        "use_websocket": coordinator.use_websocket,
        "plant_id": coordinator.plant_id,
    }

    if current:
        data["devices"] = {
            serial: {
                "product_type": str(device.product_type),
                "model": device.model,
                "plant_name": device.plant_name,
                "status": device.status,
                "firmware_version": device.firmware_version,
            }
            for serial, device in current.devices.items()
        }
        data["snapshots"] = {
            serial: {
                "product_type": str(snapshot.product_type),
                "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
                "pv_power": snapshot.pv.power,
                "battery_soc": snapshot.battery.soc,
                "battery_soh": snapshot.battery.soh,
                "battery_power": snapshot.battery.power,
                "grid_power": snapshot.ac_in.power,
                "total_energy": snapshot.totals.total_kwh,
            }
            for serial, snapshot in current.snapshots.items()
        }
        data["alerts"] = [
            {
                "id": alert.id,
                "device_sn": alert.device_sn,
                "title": alert.title,
                "severity": alert.severity,
                "active": alert.is_active,
            }
            for alert in current.alerts
        ]

    return data
