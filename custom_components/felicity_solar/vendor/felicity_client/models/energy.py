"""Energy flow model.

The shape of ``GET /device/get_energy_flow2`` was confirmed against a live
IVEM8048-II installation on 2026-10-21. The field names are **not** the
obvious ones, so they are mapped explicitly instead of heuristically:

===========  =========================================================
Canonical    Confirmed field
===========  =========================================================
``pv``       ``pvTotalPower``
``load``     ``acTotalOutActPower`` (also ``totalConsumPower``)
``battery``  ``emsPower`` (also ``batteryCharging``/``batteryDischarge``)
``grid``     ``meterPower`` (also ``acTtlInPower``, ``ctPower``)
===========  =========================================================

Every other numeric field of the payload stays available through
:attr:`EnergyFlow.values`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .._coerce import to_float, to_str

__all__ = ["EnergyFlow"]

#: Canonical flow -> the confirmed field names, in order of preference.
_FLOW_FIELDS: dict[str, tuple[str, ...]] = {
    "pv": ("pvTotalPower", "pvPower", "pvPowerConvertion"),
    "load": ("acTotalOutActPower", "totalConsumPower", "loadPowerConvertion"),
    "battery": ("emsPower", "batteryCharging", "bmsPower", "batPowerConvertion"),
    "grid": ("meterPower", "acTtlInPower", "totalAcTtlInPower", "ctPower"),
    "generator": ("genPower", "genPowerConvertion"),
    "smart_load": ("smartLoadTotalPower", "familyLoad"),
}

#: Keys that must never be mistaken for a flow value.
_IGNORED_KEY_TOKENS = ("sn", "id", "time", "date", "status", "type", "code", "flag")


@dataclass(frozen=True, slots=True)
class EnergyFlow:
    """Instantaneous energy flows of a plant or device.

    The **sign convention**, confirmed on a live installation: a positive
    battery power means the battery is **charging**; a positive grid power
    means the grid is **supplying** the installation.
    """

    device_sn: str | None = None
    plant_id: str | None = None
    pv_power: float | None = None
    load_power: float | None = None
    battery_power: float | None = None
    grid_power: float | None = None
    grid_ac_input_power: float | None = None
    generator_power: float | None = None
    smart_load_power: float | None = None
    values: Mapping[str, float] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> EnergyFlow:
        """Build a flow from a ``/device/get_energy_flow2`` payload."""
        values: dict[str, float] = {}
        for key, value in payload.items():
            lowered = key.lower()
            if any(token in lowered for token in _IGNORED_KEY_TOKENS):
                continue
            number = to_float(value)
            if number is not None:
                values[key] = number

        def pick(canonical: str) -> float | None:
            for name in _FLOW_FIELDS[canonical]:
                number = values.get(name)
                if number is not None:
                    return number
            return None

        return cls(
            device_sn=to_str(payload.get("deviceSn")),
            plant_id=to_str(payload.get("plantId")),
            pv_power=pick("pv"),
            load_power=pick("load"),
            battery_power=pick("battery"),
            grid_power=pick("grid"),
            # La entrada en CA: es el consumo desde la red del inversor.
            grid_ac_input_power=to_float(payload.get("acTtlInPower")),
            generator_power=pick("generator"),
            smart_load_power=pick("smart_load"),
            values=values,
            raw=dict(payload),
        )

    def value(self, name: str, default: float | None = None) -> float | None:
        """Look up a raw numeric field by its original name."""
        return self.values.get(name, default)

    @property
    def field_count(self) -> int:
        """Number of numeric fields the payload exposed."""
        return len(self.values)
