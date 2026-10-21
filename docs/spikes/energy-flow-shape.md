# Spike: forma de la respuesta de energía

> **Pregunta abierta Q2** de `SPECS.md`.
> **Estado: CERRADA** — 2026-10-21, con una cuenta real.

## Veredicto

### 1. La forma de `GET /device/get_energy_flow2`

Confirmada sobre un IVEM8048-II. Los campos **no** tienen los nombres
obvios, por eso el cliente los mapea explícitamente en vez de adivinar:

| Canónico | Campo real | Valor de ejemplo |
|---|---|---|
| `pv` | `pvTotalPower` | 3138 W |
| `load` | `acTotalOutActPower` (también `totalConsumPower`) | 850 W |
| `battery` | `emsPower` (también `batteryCharging`) | 2184 W |
| `grid` | `meterPower` (también `acTtlInPower`, `ctPower`) | 0 W |
| `generator` | `genPower` | 0 W |
| `smart_load` | `smartLoadTotalPower` | 0 W |

> **Trampa documentada:** `smartLoadTotalPower` contiene la palabra
> "load" y **siempre vale 0**. Un mapeo por coincidencia de tokens habría
> reportado la carga como 0 W en vez de 850 W.

### 2. La convención de signos

**Confirmada con un equipo real cargando:**

| Situación | Signo observado |
|---|---|
| Batería cargando | `bmsPower` = **+2114.99**, `bmsPower` positivo |
| Batería descargando | (no observado en vivo) — se asume el simétrico |

Es decir: **positivo = la batería carga**. Y el balance cuadra:

```
pvTotalPower (3138) = acTotalOutActPower (850) + emsPower (2184) + pérdidas
```

### 3. Los contadores de importación/exportación de red

**Sí existen**, pero **no** en el snapshot del dispositivo: están en
`POST /plant/plantDetails`, que es el endpoint más rico de la API.

| Campo | Significado |
|---|---|
| `todayGridInput` | Energía importada de la red hoy |
| `todayFeedOutput` | Energía exportada a la red hoy |
| `todayBatteryCharging` / `todayBatteryDischarge` | Energía de batería hoy |
| `todayPv` / `todayLoad` / `todayTotalConsum` / `todayPvOwner` | Producción, consumo, consumo total y autoconsumo de hoy |
| `accPv` / `yearPv` | Producción FV acumulada |
| `monthPv` | Producción FV del mes |

> **Consecuencia directa:** la sección 8.3 de `SPECS.md` ("la red no tiene
> contadores") era una conclusión **incorrecta**: los contadores sí existen,
> en `plantDetails`. La implementación se ha corregido en consecuencia.

**Los contadores diarios reinician a medianoche**, así que en Home
Assistant se declaran con `state_class=TOTAL` y `last_reset` de medianoche.
`accPv` solo crece y se declara `TOTAL_INCREASING`, que es lo que necesita
el Energy Dashboard.

## Efecto en el diseño

- `EnergyFlow` mapea los campos por nombre exacto, no por heurística.
- `PlantDetails` es un modelo nuevo con los contadores de planta.
- Los sensores de planta de energía se sirven desde `plantDetails`.
- `sign_verified` sigue siendo `False` para los **flujos instantáneos**
  (el signo del flujo de carga no se ha observado descargando), pero los
  **contadores** de `plantDetails` no tienen ese problema: son magnitudes
  positivas por definición.

## Cómo reproducirlo

```bash
export FELICITY_TEST_EMAIL="..."
export FELICITY_TEST_PASSWORD="..."
export FELICITY_TEST_DEVICE_SN="..."
uv run python scripts/spike_energy_flow.py
```

## Pendiente

Observar el equipo **descargando** para confirmar el signo de
`bmsPower`/`emsPower` en ese sentido, y comprobar si `meterPower` cambia
de signo al importar y exportar de la red. Con eso se puede poner
`sign_verified: true` en los sensores de flujo.
