# SPECS — `felicity-metrics`

**Wrapper + integración Home Assistant para inversores/baterías Felicity Solar (plataforma FSolar / Shine)**

| | |
|---|---|
| Estado | Especificación revisada (v1) — lista para implementación |
| Autor | hugoaliaga |
| Stack | Python 3.11+ (asyncio), Home Assistant 2024.x+ |
| Entregables | `felicity-client` (librería) + `custom_components/felicity_solar` (HACS) |

---

## 1. Contexto y problema

Felicity Solar no expone un API público documentado. La plataforma FSolar (web en `shine.felicitysolar.com`) es una SPA Vue 3 + Axios que habla con un backend en `https://shine-api.felicitysolar.com`. Un usuario final solo tiene acceso a esa web y a la app móvil.

Para llevar las métricas del equipo a Home Assistant hoy existen dos caminos:

| Camino | Limitación |
|---|---|
| **Modbus directo** (p. ej. `partach/ha_felicity`, `comcowo/fsolar_modbus`) | Requiere cableado RS485 físico (adaptador USB/ethernet). No funciona si la instalación es solo WiFi. |
| **Cloud FSolar** | Requiere seleccionar/instalar una integración de terceros ya existente (`matheustavarestrindade/felicity_solar_hacs`), que cubre solo `HIGH_FREQUENCY_INVERTER` y `LITHIUM_BATTERY_PACK`, sin planta, sin flujo de energía, sin WebSocket, sin alarmas, con verificación SSL desactivada y con el token de API guardado en disco plano. |

**Este proyecto** construye un cliente propio, bien factorizado y testeado, del API oficial de FSolar, y una integración Home Assistant de primera clase encima.

### 1.1 Definición original (preservada)

> Planifica la creación de un wrapper, para obtener métricas de un inversor Felicity, vía la página web oficial, con una cuenta de usuario y contraseña, más una planta específica. La idea es generar un contenido para ser leído desde un Home Assistant, para crear los módulos que hagan posible llevar estas métricas a un Home Assistant y poder hacer uso de estas métricas en un Home Assistant.

---

## 2. Objetivos

| # | Objetivo | Criterio de éxito medible |
|---|---|---|
| O1 | Autenticar contra FSolar con email + contraseña | Login correcto, token cacheado, re-login automático ante expiración |
| O2 | Resolver la **planta** del usuario y sus dispositivos | El usuario elige su planta en el config flow; los sensores se asocian al `plantId` correcto |
| O3 | Exponer métricas en tiempo real del inversor, batería y controlador | `sensor.*` actualizados ≤ 60 s, con `device_class` y `state_class` correctos |
| O4 | Exponer el **flujo de energía** de la planta (PV / batería / red / carga) | Entidades que reflected PV, consumo, carga/descarga de batería e import/export de red |
| O5 | Exponer **alarmas y avisos** del equipo | Sensor de estado de alarma + entidades de alarma con atributos |
| O6 | Integrarse nativamente con el **Energy Dashboard** de HA | Entidades `total_increasing` seleccionables en el wizard de energía |
| O7 | No requerir **cableado físico** | Funciona sobre la conexión WiFi/RS485 ya existente en la instalación |
| O8 | Ser **mantenible** | API no oficial encapsulada en una capa testeable; el resto del proyecto ignora que es no oficial |

## 3. No objetivos (fuera de alcance de v1)

- **Control/lectura por Modbus directo** (hardware). Es un proyecto alternativo, no complementario.
- **Escritura de comandos** al equipo (cambiar modo de trabajo, setpoints, switches de batería). El API lo soporta (`/deviceCommand/*`) pero v1 es **estrictamente de solo lectura**. Se documenta como fase futura (§12, F5).
- **Backfill de series históricas** y agregados diarios/mesanuales para stats de larga plazo.
- **Cuentas multi-tenant / revendedor** (admin, instalador, distributor). Solo cuentas de usuario final.
- **App móvil / panel web propio**.
- **Soporte de la plataforma EMS comercial** (`/ems/*`). Se documenta la API pero no se implementa en v1.

---

## 4. Decisiones de diseño (ADR)

| ID | Decisión | Alternativa descartada | Motivo |
|---|---|---|---|
| **ADR-1** | Dos paquetes: `felicity-client` (librería async, sin dependencia de HA) + `custom_components/felicity_solar` (integración HA) | Todo dentro de `custom_components` | La lógica de API es reutilizable (Node-RED, scripts, tests unitarios sin spinning up HA) y se puede publicar en PyPI. |
| **ADR-2** | `httpx.AsyncClient` + `websockets` sobre `asyncio` nativo | `aiohttp` | `httpx` trae timeouts/retries más limpios y soporte HTTP/2; `aiohttp` obliga a `ssl=False` por defecto. `websockets` es la lib WS más mantenida. |
| **ADR-3** | **WebSocket push como transporte primario**, polling REST como fallback | Solo polling REST | La web oficial usa `wss://shine-api.felicitysolar.com/energy-flow/{deviceSn}` con push real. Evita latencia y quema menos cuota de API. |
| **ADR-4** | Verificación SSL **activada** con CA intermedia empaquetada como fallback | `ssl=False` (como hace la integración existente) | Se verificó que la cadena actual valida OK (`Verify return code: 0`). Desactivar la verificación expone credenciales de la API a MITM. Si la cadena se rompe, se empaqueta la intermedia como CA explícita, **nunca** se degrada a `ssl=False`. |
| **ADR-5** | Token persistido en el keyring de HA (`config_entry` con `entry_id` como clave), no en disco plano | JSON plano en el cwd | La integración existente escribe `data/felicitySolarToken.json` con el bearer en texto plano. En HA, `Store` con `async_encrypt` es la práctica correcta. |
| **ADR-6** | Un `ConfigEntry` por **cuenta**; la planta es un parámetro de la entrada | Un config entry por planta | Una cuenta puede tener varias plantas. Se resuelve con un selector de planta; si el usuario quiere varias, se crean varias entradas. |
| **ADR-7** | `DataUpdateCoordinator` como fuente de verdad, alimentado por un listener de WebSocket que publica al coordinator | Coordinator polling puro | Un solo camino de actualización → entidades consistentes, sin doble fetch. |
| **ADR-8** | La API no oficial se aísla detrás de una interfaz `FelicityClient` con DTOs tipados (Pydantic v2 o dataclasses) | Diccionarios crudos | Permite testear con fixtures grabados y aislar cambios del API. |
| **ADR-9** | Versiónado de la spec de la API en `docs/api-surface.md` con la fecha de captura | Nota en el README | El API no oficial cambia; hay que saber contra qué versión se construyó. |

---

## 5. Arquitectura

```
┌────────────────────────────────────────────────────────────────────┐
│  Home Assistant                                                     │
│                                                                     │
│  config_flow  →  FelicityConfigEntry (email, plant_id, scan)        │
│         │                                                           │
│         ▼                                                           │
│  coordinator.py ──► FelicityClient (felicity-client)                │
│         │                    │                                     │
│         │                    ├── AuthService   (RSA + token)       │
│         │                    ├── PlantService  (plantas)            │
│         │                    ├── DeviceService (snapshot, flow)      │
│         │                    ├── AlertService  (alarmas)            │
│         │                    └── RealtimeService (WebSocket)        │
│         │                                                          │
│         ▼                                                          │
│  sensor.py / binary_sensor.py / number.py / button.py              │
│         │                                                          │
│         ▼                                                          │
│  Energy Dashboard  ·  Lovelace  ·  Automatizaciones                │
└────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
        https://shine-api.felicitysolar.com      (REST)
        wss://shine-api.felicitysolar.com        (WebSocket push)
```

### 5.1 Capa 1 — `felicity-client` (librería)

Paquete Python independiente, sin dependencia de Home Assistant.

```
felicity-client/
├── pyproject.toml
├── src/felicity_client/
│   ├── __init__.py
│   ├── client.py          # FelicityClient: fachada de alto nivel
│   ├── auth.py            # RSA, login, caché/refresh de token
│   ├── crypto.py          # extracción de clave pública RSA
│   ├── http.py            # cliente httpx, retries, timeouts, interceptores
│   ├── realtime.py        # cliente WebSocket + reconexión
│   ├── models/
│   │   ├── common.py      # DeviceType, Plant, Device, DeviceRef
│   │   ├── snapshot.py    # SnapshotInverter / SnapshotBattery / SnapshotController
│   │   ├── energy.py      # EnergyFlow
│   │   └── alerts.py      # Alert
│   ├── services/
│   │   ├── plants.py
│   │   ├── devices.py
│   │   ├── energy.py
│   │   └── alerts.py
│   └── exceptions.py      # FelicityAuthError, FelicityAPIError, FelicityTokenExpired...
└── tests/
```

**API pública**

```python
from felicity_client import FelicityClient

async with FelicityClient(email, password) as client:
    plants = await client.list_plants()
    plant = await client.get_plant(plant_id)
    devices = await client.list_devices(plant_id)
    snap = await client.get_snapshot(device_sn)
    flow = await client.get_energy_flow(device_sn, plant_id)
    alerts = await client.list_alerts(device_sn)

    # push
    async for event in client.stream_realtime(device_sn):
        print(event.snapshot.pv_power)
```

### 5.2 Capa 2 — `custom_components/felicity_solar` (integración HA)

```
custom_components/felicity_solar/
├── __init__.py          # setup entry, unload, forwarding
├── manifest.json
├── config_flow.py       # UI: email, password, selector de planta, opción de escaneo
├── coordinator.py       # FelicityCoordinator
├── const.py
├── entity.py            # base FelicityEntity
├── sensor.py            # sensores por device_class
├── binary_sensor.py     # online/offline, estado de alarma
├── number.py            # (fase futura) setpoints
├── button.py            # (fase futura) refresh
├── diagnostics.py
├── manifest.json
├── strings.json / translations/{en,es}.json
└── icons/               # iconos por entidad
```

**Entidades HA generadas** (por dispositivo encontrado en la planta):

| Entidad | Origen | Notas |
|---|---|---|
| `sensor.felicity_<plant>_<device>_pv_power` | `pvPower` | W, `state_class=MEASUREMENT` |
| `sensor..._pv_voltage` / `_pv_current` | `pvVolt` / `pvInCurr` | V / A |
| `sensor..._pv_energy_today` | `ePvToday` | kWh, **no** `total_increasing` (se reinicia a diario) |
| `sensor..._pv_energy_total` | `ePvTotal` | kWh, `total_increasing` → Energy Dashboard |
| `sensor..._ac_grid_voltage` / `_frequency` / `_power` | `acRInVolt` / `acRInFreq` / `acRInPower` | Entrada AC (red) |
| `sensor..._ac_output_power` | `acTotalOutActPower` | W |
| `sensor..._load_percentage` | `loadPercent` | % |
| `sensor..._battery_soc` | `emsSoc` o `battSoc` | %, `state_class=MEASUREMENT` |
| `sensor..._battery_soh` | `battSoh` | % |
| `sensor..._battery_voltage` / `_current` / `_power` | `battVolt` / `battCurr` / `bmsPower` | V / A / W |
| `sensor..._battery_capacity` | `battCapacity` | kWh |
| `sensor..._battery_remaining_energy` | `remainingBatteryEnergy1` | kWh |
| `sensor..._battery_temp_max` / `_min` | `tempMax` / `tempMin` | °C |
| `sensor..._inverter_temp_max` | `devTempMax` | °C |
| `sensor..._cell_voltage_max` / `_min` | `maxVoltage2bms` / `minVoltage2bms` | V |
| `sensor..._wifi_signal` | `wifiSignal` | dBm |
| `sensor..._charging_state` | `bmsChargingState` | enum: idle / charging / discharging / unknown — **mapeo a confirmar con equipo real** (ver §15, Q9) |
| `binary_sensor..._alarm` | `/device/device_warring_list` | on/off |
| `binary_sensor..._online` | `status` del device | on/off |
| `sensor.felicity_<plant>_grid_import` / `_export` | derivado de `get_energy_flow2` | **best effort** (§8.3) |
| `sensor.felicity_<plant>_load_power` / `_pv_power` / `_battery_power` | `get_energy_flow2` | Flujo a nivel de planta |

---

## 6. Referencia de la API (verificada)

> Capturado del bundle de producción de `https://shine.felicitysolar.com` el **2026-10-21**. Se mantiene una copia de los nombres de endpoint en `docs/api-surface.md`.

### 6.1 Transporte

| | |
|---|---|
| Base REST | `https://shine-api.felicitysolar.com` |
| WebSocket | `wss://shine-api.felicitysolar.com` |
| Nodo | `INT` (internacional). Existe `EU` (europeo) → `localStorage["api_node"]` con `{nodeCode, apiAddress, wsAddress}`. Se permite override por config. |
| Timeouts | REST 15 s · WS connect 10 s · WS ping 20 s |

### 6.2 Envoltura de respuesta

```jsonc
// éxito
{ "code": 200, "data": { ... }, "message": "success" }
// error
{ "code": 10010027, "message": "RSA ciphertext error", "data": "RSA ciphertext error" }
```

> `code != 200` ⇒ error. `message` es la clave de i18n del backend, no un mensaje en inglés.

**Comportamiento crítico verificado:** una llamada sin token válido **no** devuelve 401; el gateway **responde `302 Found` con `Location: /token_expiration`**. El cliente **debe**:
1. Configurar `follow_redirects=False` en `httpx`.
2. Tratar `302 → /token_expiration` como `FelicityTokenExpired` ⇒ re-login y reintento (1 sola vez).

Ignorar esto produce bucles silenciosos de "sin datos".

### 6.3 Cabeceras obligatorias

```http
POST /device/list_device_all_type HTTP/1.1
Host: shine-api.felicitysolar.com
Authorization: Bearer_<jwt>      # el token completo, SIN prefijo "Bearer "
content-type: application/json
lang: en_US
source: WEB
Node: INT
```

> **Cabecera del token.** El token devuelto por el login ya viene con el prefijo `Bearer_`; se envía **tal cual** en la cabecera `Authorization`, **sin** añadir un `Bearer ` adicional (la web tampoco lo hace). El nombre de la cabecera es `Authorization` en la web y `authorization` en la implementación de referencia: las cabeceras HTTP son case-insensitive (RFC 9110) y el gateway (Tengine) no distingue. El cliente usa `Authorization`.
>
> **`lang`.** La web envía el idioma del navegador, con `zh_CN` por defecto. El cliente envía `en_US` explícitamente para que los mensajes de error sean legibles; es un parámetro configurable.
>
> **`Node`.** Identifica el nodo del backend (`INT` internacional, `EU` europeo). El cliente lo deriva de la configuración de nodo y lo envía siempre.

### 6.4 Autenticación

**Extracción de la clave pública RSA.** La web cifra la contraseña con RSA/ECB/PKCS1v1.5 usando una clave pública de 2048 bits embebida en el bundle de login:

```
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnAJE68pjWZmtSg6ZJs9FZugJXC6bBSluTW6mJitt...
-----END PUBLIC KEY-----
```

- **Estrategia primaria:** valor embebido como constante en `crypto.py` (`DEFAULT_PUBLIC_KEY_PEM`), con test que valida que parsea y que su fingerprint SHA-256 no cambia.
- **Estrategia de respaldo:** si el login falla con `code` de error de RSA, re-extraer la clave del bundle en vivo (parsear `index.<hash>.js` → buscar `setPublicKey(<var>)` → buscar la asignación de la variable) y reintentar **una vez**, cacheando la clave extraída con su hash.
- La clave puede rotar; por eso el respaldo existe.

**Login.**

```http
POST /userlogin
{"userName": "<email>", "password": "<base64(RSA_PKCS1v1_5(contraseña))>", "version": "1.0"}
```

Respuesta: `data.token` = `"Bearer_<JWT>"`. El JWT **no se valida por firma** (el backend no expone la clave pública de verificación); se decodifica sin verificar para extraer `exp` y usarlo como expiración. Verificado: el token es un JWT estándar con claim `exp` en epoch de segundos.

> La respuesta de error `10010027 / "RSA ciphertext error"` confirma que el cifrado RSA es **obligatorio**, no opcional.

**Persistencia del token.** Guardar `{token, exp}` cifrado. En HA, `homeassistant.helpers.storage.Store` con `async_encrypt=True` y clave derivada del `entry_id`. En la librería, exponer un `TokenStore` inyectable con una implementación `FileTokenStore` (permisos 0600) para uso fuera de HA.

### 6.5 Plantas

| Endpoint | Método | Body | Devuelve |
|---|---|---|---|
| `/plant/list_plant` | POST | `{pageNum, pageSize, plantName?}` | `{dataList:[{id, plantName, address, countryId, ...}], total}` |
| `/plant/list_plant_name` | POST | `{pageNum, pageSize, plantName?}` | lista plana de nombres (para dropdowns) |
| `/plant/list_condition_plant` | POST | `{...}` | plantas con condición de filtrado |
| `/plant/plantDetails` | POST | `{id}` | detalle de la planta |
| `/plant/getPlantClimateVo` | POST | `{plantId}` | datos climáticos (no usado en v1) |

> El `plantId` es el campo `id` de la respuesta. Es el mismo `plantId` que se usa en `/device/get_energy_flow2?deviceSn=…&plantId=…` y en `wss://…/energy-plant-flow/{plantId}`.

**Selección de planta en HA:** el config flow llama a `list_plants()` y presenta un `SelectSelector` con `plantName` como etiqueta y `id` como valor. Si la cuenta tiene exactamente una planta, se auto-selecciona y se omite el paso.

### 6.6 Dispositivos

| Endpoint | Método | Body | Notas |
|---|---|---|---|
| `/device/list_device` | POST | `{pageNum, pageSize, plantId?}` | Lista paginada con filtro de planta |
| `/device/list_device_all_type` | POST | `{pageNum, pageSize, deviceSn:"", status:"", sampleFlag:"", oscFlag:""}` | Lista plana de todos los dispositivos de la cuenta. **Referencia verificada.** |
| `/device/list_condition_device` | POST | `{...}` | Búsqueda con condiciones |
| `/device/get_device_snapshot` | POST | `{"deviceSn":"…","deviceType":"BP","dateStr":"YYYY-MM-DD HH:mm:ss"}` | Métricas en vivo. **Referencia verificada.** |
| `/device/get_energy_flow2` | GET | `?deviceSn=…&plantId=…` | Flujo de energía |
| `/device/device_warring_list` | POST | `{deviceSn?}` | Alarmas activas |
| `/device/warring/group` | POST | `{deviceSn?}` | Alarmas agrupadas |
| `/deviceWarning/update_warn_status` | POST | `{id, status}` | Marcar alarma como vista |
| `/historyWarning/list_historyData` | POST | `{deviceSn, …}` | Histórico de alarmas |

> `pageSize: 10` en la referencia puede truncar cuentas con muchos dispositivos. El wrapper **pagina hasta agotar** (`total` en la respuesta).

**`productTypeEnum`** — discriminante del snapshot:

| Valor | Significado |
|---|---|
| `HIGH_FREQUENCY_INVERTER` | Inversor de alta frecuencia (IVGM, T-REX…) |
| `LITHIUM_BATTERY_PACK` | Batería de litio (FLA, FLB, FLH…) |
| `CONTROLLER` | Controlador / cargador |
| `*` | Desconocido → se crea un dispositivo con solo atributos genéricos (no se descarta silenciosamente) |

> `productTypeEnum` **no** cubre todos los equipos: la web usa además `typeCode` y `subType` numéricos para el layout de UI. El wrapper expone los tres y no depende de `typeCode` para el mapeo.

### 6.7 Snapshot — campos de referencia

Respuesta de `/device/get_device_snapshot` (campo `data`). Verificado en producción sobre un equipo real.

**Comunes:** `deviceSn`, `deviceModel`, `deviceType`, `typeCode`, `subType`, `status`, `plantName`, `parentId`, `productTypeEnum`, `ratedPower`, `nameplateRatedPower`, `ratedEnergy`, `batteryCapacity`, `capacity`, `firmwareVersion`, `collectorSn`, `collectorSn2`, `controlVersion`, `workModeStr`, `status`, `timeZone`, `dataTime`, `dataTimeStr`, `warningCount`, `activationFlag`, `hasMaster`, `batCount`, `voltageLevel`, `inputPhaseNum`, `outputPhaseNum`, `pvChannelNum`, `reportFreq`, `wifiSignal`, `disPlayDataInfo`, `sampleFlag`, `isOwnerDevice`.

**PV:** `pvVolt`, `pvInCurr`, `pvPower`, `pvTotalPower`, `pv1Power`…`pv4Power`, `pvTotalVoltage`, `ePvToday`, `ePvTotal`.

**AC / red:** `acRInVolt`, `acRInFreq`, `acRInPower`, `acROutVolt`, `acROutCurr`, `acROutFreq`, `acTotalOutActPower`, `loadPercent`, `eLoadToday`, `eLoadTotal`.

**Batería / EMS:** `emsVoltage`, `emsCurrent`, `emsPower`, `emsSoc`, `emsSoh`, `emsCapacity`, `totalEmsCapacity`, `battVolt`, `battCurr`, `battSoc`, `battSoh`, `battCapacity`, `bmsPower`, `bmsChargingState`, `bmsState`, `remainingBatteryEnergy1`, `maxVoltage2bms`, `minVoltage2bms`, `maxVoltageNum2bms`, `minVoltageNum2bms`, `bmsVoltageList[]`, `cellTempList[]`, `cellTemp1`…`cellTemp16`, `BMSLCVolt`, `BMSLDVolt`, `BMSLCCurr`, `BMSLDCurr`, `seriesParallelStatus`.

**Temperaturas:** `tempMax`, `tempMin`, `devTempMax`, `devTempMin`.

**Totales:** `totalEnergy`, `totalEnergyUnit`, `energy`, `energyUnit`, `bmsFlag`, `bmsFlagStr`, `batBmsOnlineStr`, `ctIsOnelineStr`, `ronoffStr`, `outModStr`, `oSPriStr`, `cSPriStr`, `standStr`, `standFlag`, `grsmtr`, `electricityMeterLink`, `electricityMeterLinkStr`, `gunStateStr`.

> **Todos los valores numéricos llegan como `str` o pueden ser `null`.** El wrapper los convierte con `_safe_float` / `_safe_int` (default `None`, no `0.0` — un `0.0` inventado es indistinguible de un equipo parado y corrompe las estadísticas de HA).

### 6.8 Flujo de energía

`GET /device/get_energy_flow2?deviceSn={sn}&plantId={pid}` → instantaneous flows de la planta: PV, carga, batería, red. Complementa al snapshot con la dirección del flujo (import/export de red), que el snapshot **no** expone.

### 6.9 WebSocket (push en tiempo real)

```
wss://shine-api.felicitysolar.com/energy-flow/{deviceSn}         # snapshot por dispositivo
wss://shine-api.felicitysolar.com/energy-plant-flow/{plantId}     # flujo por planta
wss://shine-api.felicitysolar.com/device-template-flow/{plantId}/{icons}/{type}  # avanzado
```

**Protocolo verificado:**

1. Al abrir, el cliente **debe** enviar un comando de suscripción:
   ```json
   { "type": "command",
     "deviceCommand": { "deviceSn": "<sn>", "collectorSn": "<collectorSn>" } }
   ```
   Sin este mensaje no llegan datos. (En la variante de planta: `{ "type": "command", "plant": true }` o `{ "type":"command","plant":false,"deviceCommand":{...} }`.)
2. El servidor empuja mensajes con la forma:
   ```jsonc
   { "realTimeData": { "deviceSnapshot": { /* ...mismo esquema que el snapshot REST... */ } } }
   ```
   El cliente de la web lo consume vía un store Vuex (`socket/SET_REALTIMEDATA`).
3. La web **reenvía el comando de suscripción cada 10 s** como keepalive. Se replica ese comportamiento.
4. Reconexión: backoff exponencial (1 s → 2 s → 4 s → … → máx 60 s) con jitter, hasta 10 reintentos; tras eso se degrada a polling REST.

> El WebSocket **no** autentica por token en la URL (la web reutiliza la sesión del navegador). Se debe probar si el handshake exige cabecera `authorization`; si la rechaza, se encapsula el WS detrás del polling. **Tarea de spike en Fase 1 (§12).**

### 6.10 SSL / CA

Verificado el **2026-10-21**:
```
depth=0 ... CN = *.felicitysolar.com
depth=1 C = CN, O = "Beijing Xinchacha Credit Management Co., Ltd.", CN = Xcc Trust OV SSL CA
depth=2 C = PL, O = Unizeto Technologies S.A., CN = Certum Trusted Network CA
Verify return code: 0 (ok)
```
La cadena valida correctamente con `certifi`. La integración de terceros existía porque en el pasado la intermedia faltaba. **Política: verificación siempre activa**; si la intermedia desaparece, se empaqueta la intermedia en `felicity_client/certs/` y se añade a la trust store, con un test de monitorización de la cadena.

---

## 7. Modelo de datos (DTOs)

```python
# models/common.py
class DeviceType(StrEnum):
    INVERTER = "HIGH_FREQUENCY_INVERTER"
    BATTERY = "LITHIUM_BATTERY_PACK"
    CONTROLLER = "CONTROLLER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Plant:
    id: str
    name: str
    address: str | None = None
    country_id: str | None = None
    device_count: int | None = None


@dataclass(frozen=True, slots=True)
class Device:
    serial_number: str
    device_type: DeviceType
    model: str | None
    plant_id: str | None
    plant_name: str | None
    status: str | None  # "online" / "offline" / ...
    firmware_version: str | None
    raw: Mapping[str, Any]  # volcado original, para atributos HA
```

```python
# models/snapshot.py
@dataclass(frozen=True, slots=True)
class Snapshot:
    device_sn: str
    device_type: DeviceType
    timestamp: datetime
    pv: PVReadings
    ac_in: ACReadings
    ac_out: ACReadings
    battery: BatteryReadings
    thermal: ThermalReadings
    totals: EnergyTotals
    raw: Mapping[str, Any]
```

Cada sub-dataclass contiene **solo** los campos mapeados, con `float | None` y `int | None`. La normalización `str → float` ocurre en un único sitio (`_coerce.py`) y está cubierta por tests.

---

## 8. Mapeo a entidades Home Assistant

### 8.1 Reglas

- `device_class` y `state_class` obligatorios en toda entidad de energía/potencia (requisito del Energy Dashboard).
- Unidades SI nativas de HA (`UnitOfPower.WATT`, `UnitOfEnergy.KILO_WATT_HOUR`, `UnitOfElectricPotential.VOLT`, `PERCENTAGE`, `UnitOfTemperature.CELSIUS`, `SIGNAL_STRENGTH_DECIBELS_MILLIWATT`).
- `native_value` en **unidades nativas** (W, no kW). La conversión a kW se hace en la tarjeta de Lovelace, no en el sensor.
- Nombres de entidad: `sensor.felicity_{plant_slug}_{device_slug}_{metric}`.
- Atributos por entidad: `device_sn`, `model`, `firmware_version`, `plant_name`, `last_update` (ISO 8601), `source` (`websocket` | `rest`).
- `unique_id` = `f"{device_sn}_{metric_key}"` — estable, para que los historian no se dupliquen al renombrar.

### 8.2 `state_class` — el punto delicado

| Métrica | `state_class` | Razón |
|---|---|---|
| Potencias, corrientes, voltajes, SOC, SOH, temperaturas | `MEASUREMENT` | Instantáneo |
| `ePvTotal`, `eLoadTotal`, `totalEnergy` | `TOTAL_INCREASING` | Contador monotónico de vida → Energy Dashboard |
| `ePvToday`, `eLoadToday` | `MEASUREMENT` (sin `state_class` de energía) | **Se reinicia a diario.** Declararlos `TOTAL`/`TOTAL_INCREASING` rompe las estadísticas de largo plazo. Se documentan como "energía de hoy" en la tarjeta. |
| `battCapacity`, `remainingBatteryEnergy1` | `MEASUREMENT` | Capacidad nominal / restante, no flujo |

**Consecuencia:** el Energy Dashboard no puede usar "energía de hoy" para la estadística diaria; debe usar los contadores `total_increasing` de por vida + la función de statistics de HA.

### 8.3 Red (import/export) — limitación conocida

El snapshot **no** expone contadores de import/export de red. Las opciones, en orden de preferencia:

1. **`get_energy_flow2`** → flujos instantáneos de red. Con `state_class=MEASUREMENT` se puede alimentar un `utility_meter` de HA (in/out) que sí produce contadores `total_increasing` derivados. **Es la vía recomendada en v1.**
2. Derivar por balance `grid = load - pv - battery_discharge` — frágil con pérdidas y autoconsumo; **no** se usa como fuente primaria.
3. Si el equipo tiene un medidor de red (`electricityMeterLink` / `grsmtr` / `ctIsOnelineStr`), puede haber contadores directos: **spike en Fase 2** para confirmarlo con un equipo real.

### 8.4 Energy Dashboard — mapeo propuesto

| Panel del wizard | Sensor |
|---|---|
| Solar — producción | `sensor.felicity_{plant}_pv_energy_total` (`ePvTotal`) |
| Batería — carga | `utility_meter` derivado de `bms_power` (signo) |
| Batería — descarga | `utility_meter` derivado de `bms_power` (signo) |
| Red — consumo | `utility_meter` derivado de `ac_r_in_power` |
| Red — exportación | `utility_meter` derivado del flujo de red |

> Los `utility_meter` son componentes **nativos** de HA. La integración expone las potencias instantáneas y documenta el snippet YAML de `utility_meter` en el README + en la tarjeta de Lovelace. No se reimplementa la lógica de contadores.

---

## 9. Config flow (UX)

### Paso 1 — Credenciales
`email` (TextSelector, `UserAuthentication` autocompletado) + `password` (PasswordSelector). Validación en línea: se intenta el login; si falla, `InvalidAuth`.

### Paso 2 — Planta
Se listan las plantas de la cuenta (`plantName` como etiqueta). Si hay una sola, se auto-selecciona. Opción "usar todas las plantas" → crea un `ConfigEntry` por planta (multi-entry).

### Paso 3 — Dispositivos (opcional)
Checkbox "Escanear dispositivos automáticamente" (por defecto **activado**): la integración descubre todos los dispositivos de la planta. Si se desactiva, el usuario elige los SN a exponer. Esto permite excluir una segunda batería que no interesa.

### Opciones de la entrada
| Opción | Tipo | Default | Rango |
|---|---|---|---|
| `scan_interval` | int (s) | 60 | 30 – 3600 |
| `use_websocket` | bool | `True` | — |
| `poll_interval_when_ws_down` | int (s) | 60 | 30 – 3600 |
| `enable_plant_flow` | bool | `True` | — |
| `enable_alerts` | bool | `True` | — |
| `api_node` | select | `INT` | `INT` / `EU` |

Las opciones se pueden cambiar desde la UI (options flow) sin recrear la entrada.

---

## 10. Resiliencia, reintentos y quotas

| Situación | Detección | Comportamiento |
|---|---|---|
| Token expirado | `302 → /token_expiration` o `exp` del JWT vencido | Re-login (1 reintento) + refetch. Backoff 1 s. |
| Credenciales inválidas | `code != 200` en `/userlogin` | `ConfigEntryAuthFailed` → HA muestra "reautenticar". **No** se reintenta en bucle. |
| Rate limit / 5xx | HTTP 429 / 5xx | Backoff exponencial con jitter, máx 3 intentos por llamada. |
| WebSocket caído | Cierre de conexión | Reconexión exponencial 1→60 s. Tras 10 fallos, se degrada a polling REST y se crea una `Repairs` issue. |
| Red caída | Excepción de red | `UpdateFailed` en el coordinator; las entidades pasan a `unavailable` (no a `unknown`). |
| Snapshot parcial (nulls) | `_coerce` | Los campos ausentes se omiten de la entidad; la entidad se marca `unavailable` solo si el snapshot entero falla. |
| Respuesta sin `productTypeEnum` | Validación | Se registra el SN en warning y se salta ese dispositivo, **sin** tumbar el resto. |

**Límite de ritmo del backend:** no documentado. Se implementa un `RateLimiter` interno (mínimo 1 req/s por host) y se registra en el log el número de llamadas por ciclo. El límite real debe medirse en staging durante 24 h de polling a 60 s antes de fijar el valor por defecto.

---

## 11. Testing

| Nivel | Qué | Herramienta |
|---|---|---|
| **Unit** | `_coerce` (str→float, nulls), mapeo de enums, mapeo a entidades, parsing de token, firma RSA | `pytest` + `hypothesis` (property-based sobre el coerce) |
| **Contrato (offline)** | Cada endpoint contra **fixtures JSON** capturados de producción (`tests/fixtures/*.json`), versionados | `pytest` + `respx` (mock de httpx) |
| **Integración (opt-in)** | Login real + snapshot real contra la cuenta de desarrollo | `pytest -m integration`, requiere `FELICITY_TEST_EMAIL` / `FELICITY_TEST_PASSWORD` en el entorno; **nunca** en CI público |
| **Mutación del API** | Detectar roturas: cada fixture tiene un `captured_at` y un hash del shape esperado; un test falla si el shape del API cambia | `pytest` |

**Fixtures a capturar (Fase 1):** `userlogin` (token), `list_plant`, `list_device_all_type`, `get_device_snapshot` (inversor), `get_device_snapshot` (batería), `get_device_snapshot` (controlador), `get_energy_flow2`, `device_warring_list`, `plantDetails`.

**Redactado:** los fixtures deben tener `authorization`, `deviceSn` y `plantName` enmascarados. Script `scripts/redact_fixtures.py` en el pre-commit.

---

## 12. Roadmap

### Fase 0 — Cimientos (½ día)
- [ ] Estructura del repo (monorepo: `packages/felicity-client` + `packages/homeassistant`).
- [ ] `pyproject.toml`, `ruff`, `mypy --strict`, `pytest`, `pre-commit`.
- [ ] CI: GitHub Actions (lint, types, tests) en Python 3.11/3.12/3.13.
- [ ] `docs/api-surface.md` con la lista de endpoints capturada + fecha.

**Aceptación:** `make lint && make test` verde en CI.

### Fase 1 — `felicity-client`: auth + plantas + dispositivos (2-3 días)
- [ ] `http.py` con `follow_redirects=False`, retries, timeouts, manejo del `302 → /token_expiration`.
- [ ] `crypto.py`: clave pública embebida + extracción en vivo como fallback.
- [ ] `auth.py`: login, refresh, `TokenStore` (interfaz + `FileTokenStore` 0600).
- [ ] `services/plants.py`, `services/devices.py` con paginación completa.
- [ ] Modelos + `_coerce`.
- [ ] Fixtures + tests de contrato.
- [ ] **SPIKE: ¿el handshake WS exige cabecera `authorization`?** → escribir `docs/spikes/websocket-auth.md` con el veredicto.

**Aceptación:** `list_plants()`, `list_devices()`, `get_snapshot()` funcionan contra la cuenta de dev, con tests de contrato verdes y verificación SSL activa.

### Fase 2 — `felicity-client`: energía, alarmas, WebSocket (2-3 días)
- [ ] `services/energy.py` → `get_energy_flow2`.
- [ ] `services/alerts.py` → `device_warring_list`, `warring/group`, `update_warn_status`.
- [ ] `realtime.py`: cliente WS, suscripción, keepalive 10 s, reconexión exponencial, `async for` de eventos.
- [ ] Tests de la máquina de estados de reconexión (con `websockets` mockeado).

**Aceptación:** el stream WS entrega snapshots con el mismo shape que REST; reconexión tras drop de red sin intervención manual.

### Fase 3 — Integración HA: sensores (3-4 días)
- [ ] `manifest.json` (HA 2024.x+), `const.py`, `config_flow.py` (3 pasos), `options_flow`.
- [ ] `coordinator.py` con `DataUpdateCoordinator`, alimentado por WS o polling.
- [ ] `sensor.py` con `EntityDescription` por métrica, `device_class`/`state_class`/`unit`.
- [ ] `binary_sensor.py`: online + alarma.
- [ ] Registro en `device_registry` (un device HA por dispositivo Felicity, con `identifiers` = SN) y `entity_registry`.
- [ ] `diagnostics.py` (con **reporte de secretos** de HA: credenciales fuera del volcado).
- [ ] Traducciones `en` + `es`.

**Aceptación:** instalación manual en un HA de pruebas; todas las entidades con unidades correctas; el configurador no pide escribir YAML.

### Fase 4 — Integración HA: energía, alarmas, cards, docs (2-3 días)
- [ ] Sensores de flujo de planta + `utility_meter` documentado para el Energy Dashboard.
- [ ] Entidades de alarma (sensor con `state` + atributos, y botón para marcar como vista).
- [ ] Tarjeta de Lovelace (`custom:felicity-card` o solo YAML) con flujo de energía y SOC.
- [ ] `hacs.json` + badge + README con instalación, capturas, snippet de `utility_meter`, sección "limitaciones conocidas".
- [ ] Publicación de `felicity-client` en PyPI; tag de release del componente.

**Aceptación:** Energy Dashboard muestra producción solar, batería y red sin errores; la tarjeta renderiza el flujo de energía.

### Fase 5 — (Post-v1) Control y extras
- [ ] Servicios `write` para setpoints vía `/deviceCommand/*` (con confirmación en la UI).
- [ ] Números configurables (`number.py`) para SOC mínimo/máximo.
- [ ] Estadísticas históricas vía `/storageRealtimeData/chart_storageRealtimeData_mate`.
- [ ] Soporte del nodo `EU`.
- [ ] PR a `home-assistant/core` (custom integration → no es elegible, pero sí un PR al repo de la *core integration* si se-Franzca la API; en la práctica: publicar en HACS + `awesome-home-assistant`).

---

## 13. Riesgos

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | **El API no oficial cambia sin aviso** (nombres de campo, rutas, shape del login) | Alto | Capa de aislamiento + fixtures de contrato + `docs/api-surface.md` fechado + integrador que degrade a `unavailable` en vez de romper HA |
| R2 | **Rotación de la clave RSA** | Alto | Clave embebida + extracción en vivo como fallback + test de fingerprint |
| R3 | **Bloqueo/rate limit de la cuenta** | Medio | Rate limiter, backoff, caché de token, no re-loguear en cada ciclo |
| R4 | **Ruptura de la cadena TLS** (ya ocurrió una vez) | Medio | Verificación activa + intermedia empaquetada + test de monitorización; **nunca** `ssl=False` |
| R5 | **El WebSocket no es accesible sin sesión de navegador** | Medio | Spike en Fase 1; fallback a polling ya diseñado |
| R6 | **Contadores "today" que se reinician** contaminan estadísticas | Medio | `state_class` correcto (§8.2) + `utility_meter` para los acumulados |
| R7 | **ToS / uso no autorizado** | Medio | Solo lectura, sin scraping masivo, sin revender datos; documentar la ausencia de API oficial; sin credenciales en el repo |
| R8 | **Password del usuario almacenado en HA** | Medio | `config_entry` cifrado por HA; `diagnostics` redactado; nunca en logs ni en el volcado de diagnóstico |
| R9 | **Duplicidad con la integración existente** (`felicity_solar_hacs`) | Bajo | Diferenciarse por: planta, energía, WS, alarmas, calidad de código, librerías separadas |
| R10 | **Un solo SNAPSHOT por dispositivo no cubre la planta completa** (inversor ≠ planta) | Bajo | `get_energy_flow2` + `energy-plant-flow` WS; devices registrados como `device` HA separados |

---

## 14. Estructura del repositorio

```
felicity-metrics/
├── SPECS.md                     # este documento
├── README.md
├── LICENSE                      # MIT
├── Makefile
├── .pre-commit-config.yaml
├── packages/
│   ├── felicity-client/
│   │   ├── pyproject.toml
│   ├── src/felicity_client/…
│   └── tests/…
│   └── homeassistant/
│       ├── hacs.json
│       └── custom_components/felicity_solar/…
├── docs/
│   ├── api-surface.md           # endpoints + fecha de captura
│   ├── entity-map.md            # tabla campo API → entidad HA
│   └── spikes/
│       ├── websocket-auth.md
│       └── energy-flow-shape.md
├── scripts/
│   ├── capture_fixtures.py      # captura + redactado
│   └── redact_fixtures.py
└── .github/workflows/ci.yml
```

---

## 15. Preguntas abiertas (requieren respuesta o spike)

| # | Pregunta | Cómo se resuelve |
|---|---|---|
| Q1 | ¿El handshake del WebSocket acepta `authorization` sin cookie de sesión? | Spike Fase 1 |
| Q2 | ¿Qué campos exactos devuelve `get_energy_flow2` y con qué signo? | Spike Fase 1 (grabar con el equipo real) |
| Q3 | ¿Hay contadores de import/export de red en algún campo del snapshot? (`electricityMeterLink`, `grsmtr`) | Spike Fase 1 |
| Q4 | ¿Cuál es el límite de peticiones por minuto del backend? | Medir en staging tras 24 h de polling a 60 s |
| Q5 | ¿El nodo `EU` (`eu.felicitysolar.com` / otro API host) comparte el esquema de auth? | Spike Fase 2 |
| Q6 | ¿Se admite autenticación de 2 factores (SMS/email)? El login tiene `verification/get_email_code` | Revisar antes de dar por cerrado el flujo de config |
| Q7 | ¿La cuenta objetivo es de un usuario final o de un instalador con varias plantas? | Definir con el usuario final |
| Q8 | ¿Se quiere soporte de plantas de la plataforma **EMS comercial** (`/ems/*`)? | Decisión de producto, post-v1 |
| Q9 | ¿Cuál es el mapeo exacto de `bmsChargingState` (0/1/2/…) y de `bmsState`? La integración de referencia solo conoce `0=idle` y `1=charging`; el valor "discharging" queda sin confirmar | Spike Fase 1 con un equipo en carga y en descarga |

---

## 16. Criterio de "hecho" (Definition of Done) de v1

1. `pip install felicity-client` funciona y `list_plants()` + `get_snapshot()` devuelven datos reales.
2. La integración HA se instala por HACS y se configura **sin YAML** (email, password, planta).
3. Existen entidades para: PV (V/A/W/Wh), AC entrada y salida, batería (V/A/W/SOC/SOH/capacidad/temperaturas), carga (%), energía total y de hoy, flujo de planta y estado de alarma.
4. Todas las entidades de energía tienen `device_class` + `state_class` + unidad correctos; el Energy Dashboard acepta producción solar, batería y red.
5. El WebSocket es el transporte primario y el polling REST es el fallback; ambos paths están cubiertos por tests.
6. Las credenciales no aparecen en logs, en `diagnostics` ni en el repositorio.
7. La verificación TLS está activa; hay un test que falla si la cadena del API deja de validar.
8. `docs/api-surface.md` está fechado y coincide con los fixtures.
9. README con instalación, capturas, limitaciones conocidas y snippet de `utility_meter`.
10. CI verde: `ruff`, `mypy --strict`, `pytest` (unit + contrato).

---

*Documento generado el 2026-10-21. Los detalles de la API fueron verificados contra el bundle de producción de `shine.felicitysolar.com` y contra la integración de referencia `matheustavarestrindade/felicity_solar_hacs`. Re-verificar tras cambios en el frontend de FSolar.*
