"""Typed models for the Felicity Solar client."""

from __future__ import annotations

from .alerts import Alert, AlertGroup
from .common import Device, DeviceType, Plant, ProductType
from .energy import EnergyFlow
from .plant_details import PlantDetails
from .snapshot import (
    ACReadings,
    BatteryReadings,
    EnergyTotals,
    PVReadings,
    Snapshot,
    ThermalReadings,
)

__all__ = [
    "ACReadings",
    "Alert",
    "AlertGroup",
    "BatteryReadings",
    "Device",
    "DeviceType",
    "EnergyFlow",
    "EnergyTotals",
    "PVReadings",
    "Plant",
    "PlantDetails",
    "ProductType",
    "Snapshot",
    "ThermalReadings",
]
