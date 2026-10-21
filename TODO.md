# TODO — felicity-metrics

> Estado de avance de la integración **Felicity Solar** para Home Assistant.
> Última actualización: **2026-10-21**.

## Estado general

| Fase | Estado | Nota |
|---|---|---|
| 0 — Cimientos (repo, tooling, CI) | ✅ | `uv`, `ruff`, `mypy --strict`, `pytest`, pre-commit, 2 workflows de CI |
| 1 — `felicity-client`: auth, plantas, dispositivos | ✅ | Login RSA, rotación de clave, paginación completa |
| 2 — `felicity-client`: energía, alarmas, WebSocket | ✅ | `aiohttp` en vez de `websockets` (HA ya lo trae) |
| 3 — Integración HA: sensores | ✅ | 163 tests de librería + 25 de integración |
| 4 — Integración HA: energía, alarmas, docs | ✅ | Contadores de planta, Energy Dashboard listo |
| 5 — Control por comandos (post-v1) | ⏳ | El API lo soporta, v1 es solo lectura |

**Instalado y funcionando** en el Home Assistant real: 63 entidades con
datos en vivo, planta "Antares" (IVEM8048-II + FLA48100-EU).

---

## Hecho

### API de FSolar (verificada contra una cuenta real)

- [x] Login RSA/PKCS1v1.5 con re-extracción de la clave si el backend la rechaza
- [x] Token cacheado y cifrado por Home Assistant (`Store` con `async_encrypt`)
- [x] `302 → /token_expiration` (no un 401) como señal de token expirado
- [x] Tipo de producto derivado de `deviceType` (`BP`/`OG`/`PCS`)
- [x] `pvTotalPower` como total de todas lasStrings FV
- [x] Tensión de celda normalizada de mV a V
- [x] `remainingBatteryEnergy` (no `remainingBatteryEnergy1`)
- [x] Alarmas con `pageNum`/`pageSize`/`leftDate`/`rightDate` en formato completo
- [x] `plantDetails` con `plantId` (no `id`)
- [x] Contadores diarios y acumulados de planta (`todayPv`, `todayGridInput`,
      `todayFeedOutput`, `todayBatteryCharging/Discharge`, `accPv`, `monthPv`)
- [x] Fixtures capturados de la API real y redactados (sin PII)

### Preguntas abiertas — resueltas

- [x] **Q1 — WebSocket**: el handshake funciona y acepta el token, pero el
      servidor **no empuja frames** para este equipo. El polling REST es el
      camino garantizado. → [`docs/spikes/websocket-auth.md`](docs/spikes/websocket-auth.md)
- [x] **Q2 — Flujo de energía**: nombres de campo y convención de signos
      confirmados en vivo. → [`docs/spikes/energy-flow-shape.md`](docs/spikes/energy-flow-shape.md)
- [x] **Q3 — Contadores de red**: **sí existen**, en `plantDetails` (no en el
      snapshot). La conclusión original del spec era incorrecta y se corrigió.

### Home Assistant

- [x] Config flow por UI: email, contraseña, selección de planta
- [x] Options flow: intervalo, WebSocket, flujo de planta, alarmas
- [x] 63 entidades: inversor, batería, planta, binarios
- [x] `device_class` / `state_class` / unidades correctos
- [x] Contadores diarios como `TOTAL` con `last_reset` de medianoche
- [x] `plant_pv_energy_total` como `total_increasing` → Energy Dashboard
- [x] Diagnósticos sin credenciales
- [x] Traducciones `en` + `es`
- [x] Cliente vendorizado: HACS instala todo sin `pip install`

### Repositorio

- [x] `haliaga1/hassio-felicity` con `master` y `develop`
- [x] Estructura compatible con HACS (`custom_components/` en la raíz)
- [x] Instalación real verificada vía la API websocket de HACS
- [x] Recetas de HACS: `scripts/hacs_client.py`

---

## En curso

- [ ] Confirmar el signo del flujo **descargando** → poner
      `sign_verified: true` en los sensores de flujo.

---

## Hecho en esta iteración (2026-10-21)

### Selección de planta y cuentas

- [x] `unique_id = email:plant_id` → una cuenta puede exponer **varias
      plantas** y una planta puede alcanzarse desde varias cuentas
- [x] Selector de planta en el config flow (ya existía) con las **dos
      plantas reales** listadas: Antares y Antupirén
- [x] Acción **"Agregar otra cuenta o planta"** en el options flow:
      arranca un segundo config flow sin pasar por "Añadir integración"
- [x] `async_step_reconfigure` → mover una entrada a otra planta con el
      botón **Reconfigure** estándar de HA

### Panel de Energía

- [x] Configurado por API con `energy/save_prefs`:
      - **Solar** → `sensor.antares_plant_pv_energy_total` (`total_increasing`)
        + `sensor.antares_plant_pv_power` como tasa
      - **Batería** → `sensor.antares_plant_battery_charging_total` /
        `..._discharging_total`
      - **Red** → se conserva la del usuario (`sensor.consumo_electrico_total`)
        y se añade la exportación de la planta
- [x] `energy/validate` → **sin errores** en las tres fuentes
- [x] Contadores de **por vida** para red y batería, acumulados a partir
      de los diarios del API y **persistidos** (sobreviven a un reinicio)

### Calidad

- [x] Nombres de dispositivo legibles (el modelo en vez del número de serie)
- [x] SOHReported como `unknown` cuando el equipo no lo mide (0 % es imposible)
- [x] Traducciones de los contadores de por vida (sin ellas los ids salían
      como `sensor.antares_energy`)
- [x] Fixtures redactados también de PII (`realName`, `custodian`, `ownerName`)
- [x] README con las instrucciones de instalación por API

### Repositorio y herramientas

- [x] `TODO.md` con el estado de avance
- [x] Proyecto indexado con **codebase-memory-mcp**: 5006 nodos, 9068
      aristas, 17 rutas del API detectadas
- [x] Artefacto del grafo commiteado (`.codebase-memory/graph.db.zst`)
- [x] `scripts/hacs_client.py` → instalar y actualizar por API

---

## Pendiente

### Hecho en la segunda iteración (2026-10-21)

- [x] **Segunda planta añadida** (Antupirén) con su propia entrada: el
      `unique_id` es `email:plant_id`, así que una cuenta expone varias plantas
- [x] **Sensores agregados** de todas las plantas
      (`sensor.felicity_solar_total_*_all_plants`): el Energy Dashboard de HA
      es único para toda la instancia
- [x] **Backfill del recorder** (`scripts/backfill_statistics.py`): el API
      publica la producción del día y el total de por vida, y su diferencia es
      exactamente lo producido desde medianoche → el panel muestra la cifra
      real desde el primer día en vez de 0 kWh
- [x] Panel de Energía configurado con el agregado, validado sin errores

- [x] **Dashboard por planta** (`scripts/create_plant_dashboard.py`):
      una vista por planta con su producción acumulada, su potencia y sus
      contadores, más una vista de resumen. Las entidades se descubren en
      caliente, no están escritas a mano
- [x] **Panel de Energía con una fuente solar por planta**: Home Assistant
      solo limita a 1 la fuente de red, así que cada planta entra como
      fuente solar propia y el gráfico las separa

### Prioridad alta

- [ ] Tarjeta de Lovelace propia (flujo de energía + SOC)
- [ ] `utility_meter` equivalente para cuando la nube no dé contadores
- [ ] Publicar `felicity-client` en PyPI
- [ ] Release de GitHub con tag semántico (HACS lo usa para versionar)

### Prioridad media

- [ ] Historial: `/storageRealtimeData/chart_storageRealtimeData_mate`
- [ ] Soporte del nodo `EU` verificado contra el backend
- [ ] Servicios de escritura (`/deviceCommand/*`) — v2
- [ ] `number.py` para SOC mínimo/máximo — v2
- [ ] Soporte de la plataforma EMS comercial (`/ems/*`)

---

## Deuda técnica conocida

| # | Deuda | Impacto |
|---|---|---|
| D1 | El `SOH` de un inversor sin sensor de salud se reporta como `unknown` (el backend manda 0) | Bajo, ya resuelto |
| D2 | La energía de la batería (`battCapacity`) está en **Ah**, no en kWh: se expone como atributo, no como sensor | Bajo, documentado |
| D3 | `bmsState` es una máscara de bits (`9152`), no un estado legible | Bajo |
| D4 | El polling REST es el único transporte fiable: 60 s por defecto | Medio, Heredado del fabricante |
| D5 | Los fixtures se re-capturan con frecuencia (los valores cambian con el sol); las expectativas de los tests se derivan del fixture, no están fijadas | Bajo, por diseño |

---

## Cómo reproducir la instalación

```bash
# 1. HACS: añadir el repositorio personalizado
#    Settings → Devices & Services → "Custom repositories" en HACS
#    → https://github.com/haliaga1/hassio-felicity

# 2. Por API (sin tocar la UI):
export HA_URL="http://192.168.1.5:8123"
export HA_TOKEN="<long-lived access token>"
uv run python scripts/hacs_client.py "hacs/repositories/add" \
  '{"category":"integration","repository":"haliaga1/hassio-felicity"}'
uv run python scripts/hacs_client.py "hacs/repository/download" \
  '{"repository":"<id numérico>"}'

# 3. Recargar la integración y reiniciar Home Assistant
```
