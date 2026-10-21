"""Binary sensor platform for the Felicity Solar integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import FelicityCoordinator
from .entity import FelicityEntity
from .sensor import _devices_to_expose
from .vendor.felicity_client.models.alerts import Alert

_LOGGER = logging.getLogger(__name__)

ONLINE_DESCRIPTION = EntityDescription(
    key="online",
    translation_key="online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
)

ALARM_DESCRIPTION = EntityDescription(
    key="alarm",
    translation_key="alarm",
    device_class=BinarySensorDeviceClass.PROBLEM,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Felicity Solar binary sensors."""
    coordinator: FelicityCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[FelicityEntity] = []

    for device in _devices_to_expose(coordinator):
        entities.append(FelicityOnlineSensor(coordinator, device, ONLINE_DESCRIPTION))
        entities.append(FelicityAlarmSensor(coordinator, device, ALARM_DESCRIPTION))

    async_add_entities(entities)


class FelicityOnlineSensor(FelicityEntity, BinarySensorEntity):
    """Reports whether the device is online."""

    @property
    def is_on(self) -> bool | None:
        """Whether the backend reports the device as online."""
        return self._device.is_online


class FelicityAlarmSensor(FelicityEntity, BinarySensorEntity):
    """Reports whether the device has an active warning."""

    @property
    def _alerts(self) -> list[Alert]:
        """The active warnings of this device."""
        return [
            alert for alert in self.data.alerts if alert.device_sn == self._device.serial_number
        ]

    @property
    def is_on(self) -> bool | None:
        """Whether the device has at least one active warning."""
        alerts = self._alerts
        if not alerts:
            return False
        return any(alert.is_active is not False for alert in alerts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the warnings as attributes."""
        attributes = super().extra_state_attributes
        attributes["alert_count"] = len(self._alerts)
        attributes["alerts"] = [
            {
                "id": alert.id,
                "title": alert.title,
                "description": alert.description,
                "severity": alert.severity,
                "code": alert.code,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            }
            for alert in self._alerts
        ]
        return attributes
