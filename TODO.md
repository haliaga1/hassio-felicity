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

- [ ] **Selección de planta**: el `unique_id` es `email` → hoy no se puede
      añadir una **segunda planta de la misma cuenta**. Debe pasar a
      `email:plant_id`.
- [ ] **Añadir una cuenta** desde la pantalla de la integración, sin pasar
      por "Añadir integración".

---

## Pendiente

### Prioridad alta

- [ ] **Configurar el panel de Energía** de Home Assistant con
      `sensor.antares_plant_pv_energy_total` como fuente solar, para que el
      gráfico reconozca el inversor automáticamente.
- [ ] `unique_id = email:plant_id` → permitir varias plantas por cuenta.
- [ ] Botón/acción "Agregar otra cuenta o planta" en la página de la
      integración.
- [ ] `async_step_reconfigure` para cambiar de planta sin borrar la entrada.
- [ ] Confirmar el signo del flujo **descargando** → poner
      `sign_verified: true` en los sensores de flujo.

### Prioridad media

- [ ] Tarjeta de Lovelace propia (flujo de energía + SOC) o un dashboard YAML
- [ ] Snippet de `utility_meter` en el README para batería y red
- [ ] `sensor` de la carga de la batería con signo normalizado
- [ ] Publicar `felicity-client` en PyPI
- [ ] Release de GitHub con tag semántico (HACS lo usa para versionar)

### Prioridad baja

- [ ] Soporte del nodo `EU` verificado contra el backend
- [ ] Historial: `/storageRealtimeData/chart_storageRealtimeData_mate`
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
