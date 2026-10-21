# Spike: forma de la respuesta de energía

> **Pregunta abierta Q2** de `SPECS.md`.
> **Estado:** abierta — requiere una cuenta real.

## Qué hay que determinar

1. La **forma exacta** de la respuesta de `GET /device/get_energy_flow2`.
2. La **convención de signos** de cada flujo.
3. Si existe algún **contador** de importación/exportación de red.

## Por qué importa

El snapshot de `/device/get_device_snapshot` **no** expone contadores de red.
Para alimentar el panel "Red" del Energy Dashboard hace falta una de estas
vías:

| Vía | Estado |
|---|---|
| `get_energy_flow2` → flujos instantáneos → `utility_meter` | Implementada, **signo sin verificar** |
| Derivado por balance `load - pv - batería` | Descartada: frágil con pérdidas y autoconsumo |
| Contadores directos en el snapshot (`electricityMeterLink`, `grsmtr`, `ctIsOnelineStr`) | Sin explorar |

## Qué se sabe hasta ahora

Los campos `electricityMeterLink`, `electricityMeterLinkStr`, `grsmtr` y
`ctIsOnelineStr` aparecen en el snapshot de un inversor, pero sus valores en
la instalación de referencia son `0` y `"None"`, es decir, **no hay medidor
de red conectado**. Con un medidor presente podrían aparecer contadores
directos.

## Cómo reproducirlo

```bash
export FELICITY_TEST_EMAIL="..."
export FELICITY_TEST_PASSWORD="..."
export FELICITY_TEST_DEVICE_SN="..."
uv run python scripts/spike_energy_flow.py
```

El script imprime la respuesta cruda de `get_energy_flow2` y de
`get_device_snapshot`, y marca qué claves contienen valores numéricos.

## Criterio de éxito

- [ ] La forma de la respuesta está documentada en `docs/api-surface.md`.
- [ ] La convención de signos está confirmada **con un equipo cargando y
      otro descargando**.
- [ ] Los sensores de planta pueden declarar `sign_verified: true`.

## Impacto en el diseño

`FelicityPlantSensorEntityDescription.sign_verified` ya existe y vale
`false`. Cuando el spike se cierre, se cambia a `true` y la documentación
de `docs/entity-map.md` se actualiza.
