# Superficie de la API de FSolar (Shine)

> **Capturado:** 2026-10-21
> **Fuente:** bundle de producción de `https://shine.felicitysolar.com` (300+ chunks JS)
> **Verificado en vivo:** `POST /userlogin` (error RSA), `GET /device/list_device_all_type` (sin token), cadena TLS.
> **Estado:** API **no oficial**. No hay contrato de estabilidad.

Este documento existe para saber **contra qué versión del API** se construyó el
cliente. Si el frontend de FSolar cambia, este archivo y los fixtures de
contrato son la referencia para detectar la rotura.

---

## 1. Transporte

| | |
|---|---|
| Base REST | `https://shine-api.felicitysolar.com` |
| WebSocket | `wss://shine-api.felicitysolar.com` |
| Nodo internacional | `INT` |
| Nodo europeo | `EU` (configurable; se resuelve desde `localStorage["api_node"]` → `{nodeCode, apiAddress, wsAddress}`) |
| Servidor | Tengine (CDN Alibaba) |
| TLS | Cadena completa verificada (`*.felicitysolar.com` ← `Xcc Trust OV SSL CA` ← `Certum Trusted Network CA`). `Verify return code: 0` |

---

## 2. Envoltura de respuesta

```jsonc
// éxito
{ "code": 200, "data": { ... }, "message": "success" }

// error
{ "code": 10010027, "message": "RSA ciphertext error", "data": "RSA ciphertext error" }
```

- `code != 200` ⇒ error. `message` es una **clave de i18n**, no un texto en inglés.
- Sin token válido, el gateway **no** devuelve 401: responde
  `302 Found` + `Location: /token_expiration`. Hay que usar
  `follow_redirects=False` y tratar ese 302 como *token expirado*.

---

## 3. Cabeceras

| Cabecera | Valor | Nota |
|---|---|---|
| `Authorization` | `Bearer_<jwt>` | El token ya trae el prefijo `Bearer_`; **no** añadir otro `Bearer `. |
| `content-type` | `application/json` | |
| `lang` | `en_US` | La web usa el idioma del navegador, `zh_CN` por defecto. |
| `source` | `WEB` | |
| `Node` | `INT` \| `EU` | Nodo del backend. |

Los nombres de cabecera son case-insensitive (RFC 9110); la web usa
`Authorization` y la implementación de referencia `authorization`.

---

## 4. Autenticación

### `POST /userlogin`

```jsonc
{ "userName": "<email>",
  "password": "<base64(RSA_PKCS1v1_5(contraseña_utf8))>",
  "version": "1.0" }
```

Respuesta: `data.token` = `"Bearer_<JWT>"`.

El cifrado RSA es **obligatorio** — enviado en claro devuelve
`{"code":10010027,"message":"RSA ciphertext error"}`.

**Clave pública RSA (SPKI, 2048 bit, base64):**

```
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnAJE68pjWZmtSg6ZJs9FZugJXC6bBSluTW6mJ
ttOLOaljrdErVnM5DNN+YFzpB9pAysTErjY1bnSVuEwQSwptnqUji7Ch2qMj2n+0eCp8p6vtSh7/tFr2ul
8nDRtkoswLANAIwtUk/G85ipMpmY1W642LImnEJmGkkddlbjbjxJTZWR5hc/d9cPWb+AR77LxFFrMik3c
+44v1kQlIPFP6EjIbOvt/Lv7fHWD9JI/YzN4y1gK7C/VQdNGuikQyNg+5W3rg9ecYf9I5uLAQwY/hxeI3l
bNsErebqKe2EbJ8AwcNIC0lDBz53Sq0ML89QapEuy3fB+upuctxLULVDCbNwIDAQAB
```

En el frontend se inyecta con `setPublicKey(<var>)`. El cliente la embebe como
constante y, si el login falla con error de RSA, re-extrae la clave del bundle
en vivo (una vez) y reintenta.

### Expiración del token

El token es un JWT estándar. El backend **no** expone la clave pública de
verificación, así que el cliente decodifica **sin verificar la firma** y usa el
claim `exp` (epoch, segundos) como expiración.

---

## 5. Endpoints usados por el cliente

### Plantas

| Endpoint | Método | Body |
|---|---|---|
| `/plant/list_plant` | POST | `{pageNum, pageSize, plantName?}` |
| `/plant/list_plant_name` | POST | `{pageNum, pageSize, plantName?}` |
| `/plant/list_condition_plant` | POST | — |
| `/plant/plantDetails` | POST | `{id}` |
| `/plant/getPlantClimateVo` | POST | `{plantId}` |
| `/plant/collect_plant` / `un_collect_plant` | POST | `?plantId=` |

### Dispositivos

| Endpoint | Método | Body / query |
|---|---|---|
| `/device/list_device` | POST | `{pageNum, pageSize, plantId?}` |
| `/device/list_device_all_type` | POST | `{pageNum, pageSize, deviceSn:"", status:"", sampleFlag:"", oscFlag:""}` |
| `/device/list_condition_device` | POST | — |
| `/device/get_device_snapshot` | POST | `{"deviceSn":"…","deviceType":"BP","dateStr":"YYYY-MM-DD HH:mm:ss"}` |
| `/device/get_energy_flow2` | GET | `?deviceSn=…&plantId=…` |
| `/device/device_warring_list` | POST | `{deviceSn?}` |
| `/device/warring/group` | POST | `{deviceSn?}` |
| `/deviceWarning/update_warn_status` | POST | `{id, status}` |

### Alarmas / histórico

| Endpoint | Método |
|---|---|
| `/historyWarning/list_historyData` | POST |
| `/historyWarning/getHistoryDataList` | POST |
| `/historyWarning/get_history_warning_details` | POST |
| `/historyWarning/get_history_data_details` | POST |

### Tiempo real (WebSocket)

```
wss://shine-api.felicitysolar.com/energy-flow/{deviceSn}
wss://shine-api.felicitysolar.com/energy-plant-flow/{plantId}
wss://shine-api.felicitysolar.com/device-template-flow/{plantId}/{icons}/{type}
```

**Protocolo:**

1. Tras el handshake, el cliente **debe enviar** un comando de suscripción:
   ```json
   { "type": "command",
     "deviceCommand": { "deviceSn": "<sn>", "collectorSn": "<collectorSn>" } }
   ```
   Variante de planta: `{ "type": "command", "plant": true }` o
   `{ "type": "command", "plant": false, "deviceCommand": { … } }`.
2. El servidor empuja:
   ```jsonc
   { "realTimeData": { "deviceSnapshot": { /* mismo shape que el snapshot REST */ } } }
   ```
3. La web **reenvía el comando de suscripción cada 10 s** como keepalive.

> **Pendiente (Q1):** la web reutiliza la cookie de sesión del navegador. Hay
> que confirmar si el handshake acepta la cabecera `Authorization` sin cookie.
> Ver [`docs/spikes/websocket-auth.md`](spikes/websocket-auth.md).

---

## 6. Tipos de producto

| `productTypeEnum` | Significado |
|---|---|
| `HIGH_FREQUENCY_INVERTER` | Inversor de alta frecuencia (IVGM, T-REX…) |
| `LITHIUM_BATTERY_PACK` | Batería de litio (FLA, FLB, FLH…) |
| `CONTROLLER` | Controlador / cargador |
| *otro* | Desconocido → dispositivo genérico (no se descarta) |

La web usa además `typeCode` y `subType` numéricos para el layout de UI; el
cliente no depende de ellos para el mapeo.

---

## 7. Campos del snapshot

Ver `docs/entity-map.md` para el mapeo completo a entidades de HA.

**Comunes:** `deviceSn`, `deviceModel`, `deviceType`, `typeCode`, `subType`,
`status`, `plantName`, `parentId`, `productTypeEnum`, `ratedPower`,
`nameplateRatedPower`, `ratedEnergy`, `batteryCapacity`, `capacity`,
`firmwareVersion`, `collectorSn`, `collectorSn2`, `controlVersion`,
`workModeStr`, `timeZone`, `dataTime`, `dataTimeStr`, `warningCount`,
`activationFlag`, `hasMaster`, `batCount`, `voltageLevel`, `inputPhaseNum`,
`outputPhaseNum`, `pvChannelNum`, `reportFreq`, `wifiSignal`, `sampleFlag`,
`isOwnerDevice`.

**PV:** `pvVolt`, `pvInCurr`, `pvPower`, `pvTotalPower`, `pv1Power`…`pv4Power`,
`pvTotalVoltage`, `ePvToday`, `ePvTotal`.

**AC / red:** `acRInVolt`, `acRInFreq`, `acRInPower`, `acROutVolt`,
`acROutCurr`, `acROutFreq`, `acTotalOutActPower`, `loadPercent`, `eLoadToday`,
`eLoadTotal`.

**Batería / EMS:** `emsVoltage`, `emsCurrent`, `emsPower`, `emsSoc`, `emsSoh`,
`emsCapacity`, `totalEmsCapacity`, `battVolt`, `battCurr`, `battSoc`,
`battSoh`, `battCapacity`, `bmsPower`, `bmsChargingState`, `bmsState`,
`remainingBatteryEnergy1`, `maxVoltage2bms`, `minVoltage2bms`,
`maxVoltageNum2bms`, `minVoltageNum2bms`, `bmsVoltageList[]`,
`cellTempList[]`, `cellTemp1`…`cellTemp16`, `BMSLCVolt`, `BMSLDVolt`,
`BMSLCCurr`, `BMSLDCurr`, `seriesParallelStatus`.

**Térmicas:** `tempMax`, `tempMin`, `devTempMax`, `devTempMin`.

**Totales:** `totalEnergy`, `totalEnergyUnit`, `energy`, `energyUnit`,
`bmsFlag`, `bmsFlagStr`, `batBmsOnlineStr`, `ctIsOnelineStr`, `ronoffStr`,
`outModStr`, `oSPriStr`, `cSPriStr`, `standStr`, `standFlag`, `grsmtr`,
`electricityMeterLink`, `electricityMeterLinkStr`, `gunStateStr`.

> **Todos los valores numéricos llegan como `str` y pueden ser `null`.** El
> cliente los convierte con un único coercor y devuelve `None` (no `0.0`): un
> `0.0` inventado es indistinguible de un equipo parado y corrompe las
> estadísticas de Home Assistant.

---

## 8. Endpoints del API **no** usados en v1

Descartados por ser de administración, instalador o back-office:

`/adminuser/*`, `/ems/*`, `/points/*`, `/finance/*`, `/goods/*`, `/warehouse*`,
`/workorder*`, `/repair*`, `/csip*`, `/feedBack*`, `/deviceUpdate*`,
`/deviceOtaConfig*`, `/deviceCommand/*` (escritura), `/otaUpgradeTask*`,
`/powerPrediction`, `/greenPowerPlan*`, `/strategy*`, `/migrateUserRecord/*`,
`/oscDataInfo/*`, `/mqttLog/*`, `/syslog/*`.

Se dejan documentados aquí para que quede claro qué superficie está
deliberadamente fuera del alcance.
