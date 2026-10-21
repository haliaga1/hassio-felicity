"""Base entity for the Felicity Solar integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .vendor.felicity_client.models.common import Device, ProductType

from .const import DOMAIN
from .coordinator import FelicityCoordinator, FelicityData


def slugify(value: str) -> str:
    """Turn a name into a slug usable in an entity id."""
    cleaned = "".join(char if char.isalnum() else " " for char in value.lower())
    return "-".join(cleaned.split()) or "felicity"


class FelicityEntity(CoordinatorEntity[FelicityCoordinator]):
    """Base class for every entity of the integration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FelicityCoordinator,
        device: Device,
        description: EntityDescription,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._device = device
        self.entity_description = description
        self._attr_unique_id = f"{device.serial_number}_{description.key}"

    @property
    def device(self) -> Device:
        """The Felicity device this entity belongs to."""
        return self._device

    @property
    def device_info(self) -> DeviceInfo:
        """The Home Assistant device registry entry."""
        identifiers = {(DOMAIN, self._device.serial_number)}
        info = DeviceInfo(
            identifiers=identifiers,
            manufacturer="Felicity Solar",
            model=self._device.model or "Felicity device",
            name=self._device.alias or self._device.serial_number,
            serial_number=self._device.serial_number,
            sw_version=self._device.firmware_version,
        )
        if self._device.plant_name:
            info["suggested_area"] = self._device.plant_name
        return info

    @property
    def data(self) -> FelicityData:
        """The current coordinator data."""
        return self.coordinator.data or FelicityData()

    @property
    def available(self) -> bool:
        """Whether the underlying device reported data recently."""
        return super().available and self._device.serial_number in self.data.snapshots

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributes shared by every Felicity entity."""
        return {
            "device_sn": self._device.serial_number,
            "plant_name": self._device.plant_name,
            "model": self._device.model,
            "firmware_version": self._device.firmware_version,
            "source": self.data.source,
        }


def product_type_label(product_type: ProductType) -> str:
    """A readable label for a product type."""
    return {
        ProductType.INVERTER: "Inverter",
        ProductType.BATTERY: "Battery",
        ProductType.CONTROLLER: "Controller",
        ProductType.UNKNOWN: "Device",
    }.get(product_type, "Device")
