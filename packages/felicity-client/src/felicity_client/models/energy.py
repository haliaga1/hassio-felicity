"""Energy flow model.

The exact shape of ``GET /device/get_energy_flow2`` has not been confirmed
against a live installation yet (open question Q2 in ``SPECS.md``). The model
therefore keeps every numeric field it finds addressable by name, while
exposing the most likely canonical names as typed properties.

The canonical names are matched leniently: a key matches when it contains one
of the known tokens, so ``acRInPower``, ``gridInPower`` and ``inPower`` all
resolve to the grid power.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .._coerce import to_float, to_str

__all__ = ["EnergyFlow"]

#: Token -> canonical flow name. The first match wins, in declaration order.
_FLOW_TOKENS: tuple[tuple[str, str], ...] = (
    ("pv", "pv"),
    ("photovoltaic", "pv"),
    ("solar", "pv"),
    ("load", "load"),
    ("consumption", "load"),
    ("house", "load"),
    ("battery", "battery"),
    ("bms", "battery"),
    ("ess", "battery"),
    ("storage", "battery"),
    ("grid", "grid"),
    ("acrin", "grid"),
    ("ac_r_in", "grid"),
    ("acrinpower", "grid"),
    ("meter", "grid"),
    ("inv", "inverter"),
)

#: Keys that must never be mistaken for a flow value.
_IGNORED_KEY_TOKENS = ("sn", "id", "time", "date", "status", "type", "code", "flag")


@dataclass(frozen=True, slots=True)
class EnergyFlow:
    """Instantaneous energy flows of a plant or device.

    All values are signed the way the backend reports them; the sign
    convention (positive = flowing *into* the system) has to be confirmed
    against a live installation before it is used to drive the Energy
    Dashboard.
    """

    device_sn: str | None = None
    plant_id: str | None = None
    pv_power: float | None = None
    load_power: float | None = None
    battery_power: float | None = None
    grid_power: float | None = None
    inverter_power: float | None = None
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

        resolved: dict[str, float] = {}
        for key, number in values.items():
            lowered = key.lower()
            for token, canonical in _FLOW_TOKENS:
                if token in lowered:
                    resolved.setdefault(canonical, number)
                    break

        return cls(
            device_sn=to_str(payload.get("deviceSn")),
            plant_id=to_str(payload.get("plantId")),
            pv_power=resolved.get("pv"),
            load_power=resolved.get("load"),
            battery_power=resolved.get("battery"),
            grid_power=resolved.get("grid"),
            inverter_power=resolved.get("inverter"),
            values=values,
            raw=dict(payload),
        )

    def value(self, name: str, default: float | None = None) -> float | None:
        """Look up a raw numeric field by its original name."""
        return self.values.get(name, default)

    @property
    def grid_import_power(self) -> float | None:
        """Grid power, positive when importing from the grid.

        The sign convention is unverified; until Q2 is resolved this simply
        mirrors :attr:`grid_power` and the caller decides the direction.
        """
        return self.grid_power

    @property
    def grid_export_power(self) -> float | None:
        """Grid export power.

        Not derivable from the current payload; returns ``None`` until the
        response shape is confirmed.
        """
        return None

    @property
    def field_count(self) -> int:
        """Number of numeric fields the payload exposed."""
        return len(self.values)
