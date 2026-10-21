# Mapa de entidades

> Correspondencia entre los campos del API de FSolar y las entidades de
> Home Assistant. Actualizado el **2026-10-21**.

## Convenciones

| Regla | Motivo |
|---|---|
| Unidad **nativa** (W, no kW) | La conversión a kW es una decisión de presentación, no del sensor. |
| `state_class=TOTAL_INCREASING` solo para contadores de por vida | El Energy Dashboard los necesita y son monotónicos. |
| `state_class=TOTAL` + `last_reset` para los contadores diarios | `ePvToday` y `eLoadToday` se reinician a medianoche. Declararlos `TOTAL_INCREASING` corrompería las estadísticas de largo plazo. HA exige `last_reset` en todo sensor `TOTAL`. |
| `state_class=None` para cantidades | La capacidad nominal y la energía restante suben y bajan: no son flujos ni contadores. |
| Un valor ausente es `None` → entidad `unavailable` | Un `0.0` inventado es indistinguible de un equipo parado. |

---

## 1. Inversor (`HIGH_FREQUENCY_INVERTER`)

| Campo API | Entidad | Unidad | `state_class` | `device_class` |
|---|---|---|---|---|
| `pvPower` | PV power | W | measurement | power |
| `pvTotalPower` | PV total power | W | measurement | power |
| `pvVolt` | PV voltage | V | measurement | voltage |
| `pvInCurr` | PV current | A | measurement | current |
| `ePvToday` | PV energy today | kWh | **total** (+`last_reset`) | energy |
| `ePvTotal` | PV energy total | kWh | **total_increasing** | energy |
| `acRInVolt` | Grid voltage | V | measurement | voltage |
| `acRInFreq` | Grid frequency | Hz | measurement | frequency |
| `acRInPower` | Grid power | W | measurement | power |
| `acROutVolt` | AC output voltage | V | measurement | voltage |
| `acROutCurr` | AC output current | A | measurement | current |
| `acTotalOutActPower` | AC output power | W | measurement | power |
| `loadPercent` | Load | % | measurement | — |
| `eLoadToday` | Load energy today | kWh | **total** (+`last_reset`) | energy |
| `eLoadTotal` | Load energy total | kWh | **total_increasing** | energy |
| `totalEnergy` | Total energy | kWh | **total_increasing** | energy |
| `tempMax` / `tempMin` | Maximum/Minimum battery temperature | °C | measurement | temperature |
| `devTempMax` | Maximum device temperature | °C | measurement | temperature |
| `wifiSignal` | Wi-Fi signal | dBm | measurement | signal_strength |
| `workModeStr` | Work mode | — | — | — |
| `emsSoc` / `battSoc` | Battery state of charge | % | measurement | battery |
| `battSoh` | Battery state of health | % | measurement | battery |
| `battVolt` / `emsVoltage` | Battery voltage | V | measurement | voltage |
| `battCurr` / `emsCurrent` | Battery current | A | measurement | current |
| `bmsPower` / `emsPower` | Battery power | W | measurement | power |
| `battCapacity` | Battery capacity | kWh | — | energy |
| `remainingBatteryEnergy1` | Battery remaining energy | kWh | — | energy |
| `bmsChargingState` | Battery charging state | — | — | enum |
| `maxVoltage2bms` / `minVoltage2bms` | Maximum/Minimum cell voltage | V | measurement | voltage |

## 2. Batería (`LITHIUM_BATTERY_PACK`)

Comparte las filas de batería de la tabla anterior, más:

| Campo API | Entidad | Unidad |
|---|---|---|
| `bmsVoltageList[]` | (atributo) celdas | V |
| `cellTempList[]` | (atributo) celdas | °C |

## 3. Controlador (`CONTROLLER`)

Comparte las filas de PV y totales del inversor.

## 4. Planta (`get_energy_flow2`)

| Campo API | Entidad | Unidad | `state_class` |
|---|---|---|---|
| `pvPower` | Plant PV power | W | measurement |
| `loadPower` | Plant load power | W | measurement |
| `batteryPower` | Plant battery power | W | measurement |
| `gridPower` | Plant grid power | W | measurement |

> **El signo no está verificado.** El backend no documenta la convención de
> signos y no se ha confirmado contra una instalación real (pregunta abierta
> **Q2**). Los sensores de planta exponen el atributo `sign_verified: false`
> y el flujo crudo en el atributo `flow`.
>
> Para derivar importación/exportación de red hay que usar un
> `utility_meter` de Home Assistant, no asumir el signo aquí.

## 5. Binarios

| Campo API | Entidad | `device_class` |
|---|---|---|
| `status` del dispositivo | Online | connectivity |
| `/device/device_warring_list` | Alarm | problem |

El sensor de alarma expone `alert_count` y una lista `alerts[]` con `id`,
`title`, `description`, `severity`, `code` y `created_at` de cada aviso.

---

## Energy Dashboard

| Panel | Sensor |
|---|---|
| Solar — producción | `sensor.<plant>_<device>_pv_energy_total` (`ePvTotal`, `total_increasing`) |
| Batería — carga / descarga | `utility_meter` sobre `battery_power` (signo del fabricante) |
| Red — consumo / exportación | `utility_meter` sobre `plant_grid_power` y `plant_load_power` |

Los sensores de planta son **instantáneos** (`MEASUREMENT`); los contadores
del Energy Dashboard se construyen con `utility_meter`, que es un componente
nativo de Home Assistant y no se reimplementa aquí.

```yaml
utility_meter:
  - name: "Casa Principal - Solar"
    source: sensor.casa_principal_inversor_principal_pv_power
    unit_of_measurement: kWh
    device_class: energy
    state_class: total_increasing
    direction: import
```

## Atributos comunes

Toda entidad lleva `device_sn`, `plant_name`, `model`, `firmware_version` y
`source` (`websocket` o `rest`), de modo que se puede saber de dónde salió
el último valor.
