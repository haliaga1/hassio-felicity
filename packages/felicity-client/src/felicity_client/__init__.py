"""Async client for the Felicity Solar FSolar (Shine) cloud API.

This library talks to the same API the official FSolar web app uses. The API
is **not public and not documented** by the vendor; see ``docs/api-surface.md``
for the endpoints this client relies on and the date they were captured.

Example::

    from felicity_client import FelicityClient

    async with FelicityClient(email, password) as client:
        for plant in await client.list_plants():
            print(plant.id, plant.name)
"""

from __future__ import annotations

from .auth import AuthService, FileTokenStore, NullTokenStore, StoredToken, TokenStore
from .client import FelicityClient
from .const import DEFAULT_LANG, DEFAULT_NODE, DEFAULT_TIMEOUT, EU_API_URL, INT_API_URL
from .exceptions import (
    FelicityAPIError,
    FelicityAuthError,
    FelicityConnectionError,
    FelicityError,
    FelicityNotFoundError,
    FelicityTokenExpiredError,
)
from .models import (
    Alert,
    AlertGroup,
    Device,
    DeviceType,
    EnergyFlow,
    Plant,
    PlantDetails,
    ProductType,
    Snapshot,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_LANG",
    "DEFAULT_NODE",
    "DEFAULT_TIMEOUT",
    "EU_API_URL",
    "INT_API_URL",
    "Alert",
    "AlertGroup",
    "AuthService",
    "Device",
    "DeviceType",
    "EnergyFlow",
    "FelicityAPIError",
    "FelicityAuthError",
    "FelicityClient",
    "FelicityConnectionError",
    "FelicityError",
    "FelicityNotFoundError",
    "FelicityTokenExpiredError",
    "FileTokenStore",
    "NullTokenStore",
    "Plant",
    "PlantDetails",
    "ProductType",
    "Snapshot",
    "StoredToken",
    "TokenStore",
    "__version__",
]
