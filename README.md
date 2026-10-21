# felicity-metrics

Métricas de inversores y baterías **Felicity Solar** en **Home Assistant**,
a través de la nube oficial de FSolar.

Este repositorio contiene dos piezas:

| Paquete | Qué es |
|---|---|
| [`packages/felicity-client`](packages/felicity-client) | Cliente async de Python para la API de FSolar. Sin dependencia de Home Assistant. |
| [`packages/homeassistant`](packages/homeassistant) | Integración de Home Assistant (HACS) construida sobre el cliente. |

La especificación completa está en [`SPECS.md`](SPECS.md).

## Estado

| Fase | Estado |
|---|---|
| 0 — Cimientos (repo, tooling, CI) | ✅ |
| 1 — `felicity-client`: auth, plantas, dispositivos | ✅ |
| 2 — `felicity-client`: energía, alarmas, WebSocket | ✅ |
| 3 — Integración HA: sensores | ✅ |
| 4 — Integración HA: energía, alarmas, docs | ✅ |
| 5 — Control por comandos (post-v1) | ⏳ |

## Empezar

### La librería

```python
import asyncio

from felicity_client import FelicityClient, FileTokenStore


async def main() -> None:
    store = FileTokenStore("~/.config/felicity/tokens.json")
    async with FelicityClient("me@example.com", "hunter2", token_store=store) as client:
        for plant in await client.list_plants():
            print(plant.id, plant.name)

        devices = await client.list_devices(plant_id=plants[0].id)
        snapshot = await client.get_snapshot(devices[0].serial_number)
        print(snapshot.battery.soc, snapshot.pv.power)


asyncio.run(main())
```

### La integración de Home Assistant

Ver [`packages/homeassistant/README.md`](packages/homeassistant/README.md).

## Documentación

| Documento | Contenido |
|---|---|
| [`SPECS.md`](SPECS.md) | Especificación completa: objetivos, ADRs, roadmap, riesgos. |
| [`docs/api-surface.md`](docs/api-surface.md) | Los endpoints del API que usa el cliente, con la fecha de captura. |
| [`docs/entity-map.md`](docs/entity-map.md) | Campo del API → entidad de Home Assistant. |
| [`docs/spikes/`](docs/spikes) | Las preguntas abiertas y cómo resolverlas. |

## Desarrollo

```bash
uv sync --all-packages --all-extras

make check          # lint + tipos + tests de la librería
make test           # solo los tests
```

Las pruebas de la integración de Home Assistant viven en su propio entorno:

```bash
uv venv --python 3.13 packages/homeassistant/.venv
VIRTUAL_ENV=packages/homeassistant/.venv uv pip install \
  "pytest-homeassistant-custom-component==0.13.316" homeassistant \
  -e packages/felicity-client
cd packages/homeassistant && .venv/bin/python -m pytest tests/ -q
```

## Advertencias

- La API de FSolar **no es pública ni está documentada**. Este proyecto
  habla el mismo idioma que la web oficial, y puede romperse sin aviso.
- La **convención de signos** de los flujos de energía no está confirmada
  contra un equipo real (pregunta abierta Q2). Los sensores de planta lo
  declaran con el atributo `sign_verified`.
- La **verificación TLS está siempre activa**. Si algún día la cadena del
  fabricante se rompe, la respuesta es empaquetar la intermedia, nunca
  desactivar la verificación.
- Este proyecto **no está afiliado** a Felicity Solar.

## Licencia

MIT
