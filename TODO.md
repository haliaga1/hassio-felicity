# TODO — felicity-metrics

> Estado de avance de la integración **Felicity Solar** para Home Assistant.
> Última actualización: **2026-10-22**.

## Estado general

| Fase | Estado | Nota |
|---|---|---|
| 0 — Cimientos (repo, tooling, CI) | ✅ | `uv`, `ruff`, `mypy --strict`, `pytest`, pre-commit, 2 workflows de CI |
| 1 — `felicity-client`: auth, plantas, dispositivos | ✅ | Login RSA, rotación de clave, paginación completa |
| 2 — `felicity-client`: energía, alarmas, WebSocket | ✅ | `aiohttp` en vez de `websockets` (HA ya lo trae) |
| 3 — Integración HA: sensores | ✅ | 166 tests de librería + 54 de integración |
| 4 — Integración HA: energía, alarmas, docs | ✅ | Contadores de planta, Energy Dashboard listo |
| 5 — Control por comandos (post-v1) | ⏳ | El API lo soporta, v1 es solo lectura |

**Instalado y funcionando** en el Home Assistant real: dos plantas
("Antares" y "Antupirén"), con el panel de Energía validado **sin errores**
y los totales del día, del mes y del año **coincidiendo con la app
oficial**.

---

## Hecho en esta iteración (2026-10-22)

### Flujo en tiempo real en la pantalla de Energía

- [x] Home Assistant 2026.10 admite **dos sensores de potencia** por fuente
      (`power_config` con `stat_rate_from` / `stat_rate_to`): se exploitó
      para el flujo bidireccional de batería y red
- [x] Sensores de potencia separados: carga y descarga de batería, entrada
      y salida de red (por planta y agregados)
- [x] Tarjeta **`power-sankey`** en la página "Felicity Solar": es el
      equivalente al "Descripción general" de la app oficial (PV, red,
      batería, cargando, carga)
- [x] Tarjeta "Flujo en tiempo real" por planta, con las seis potencias y
      el gauge del SOC
- [x] `energy/validate` → **sin errores** con el `power_config` nuevo

### Totales del panel de Energía = los de la app oficial

El error de fondo: el recorder guarda, para un sensor `total_increasing`, el
**valor acumulado** del contador al final de la hora en la columna `sum`, y
el panel lee el consumo de un periodo como la **diferencia** entre la suma
más nueva y la más antigua. El backfill importaba el *delta* de cada hora.

- [x] El backfill importa ahora el **valor acumulado** del contador
- [x] Las aperturas de mes y año se escriben en la **hora anterior** al
      periodo, para que el recorder las encuentre como la suma más antigua
- [x] Todo se reescala con el **cero del recorder** (el primer valor que
      vio del sensor), la misma escala en la que él acumula
- [x] Verificado contra la app oficial:

      | planta   | hoy (HA / app) | mes (HA / app) | año (HA / app) |
      |----------|-----------------|----------------|----------------|
      | Antares  | 3.62 / 3.91 kWh | 222.15 / 222.2 | 1295.35 / 1295.4 |
      | Antupirén| 4.74 / 5.05 kWh | 314.96 / 315.2 | 2418.86 / 2419.2 |

      (la diferencia es la producción de los últimos minutos entre las dos
      lecturas)

### Batería y red

- [x] El API publica `todayBatteryCharging` **vacío** (siempre 0): el
      contador de batería se integra ahora con la **potencia del flujo**
- [x] La historia que la batería ya tenía se siembra una sola vez desde la
      **serie de potencias** (`chart_storageRealtimeData_mate`)
- [x] `felicity-client`: `get_storage_series()` y `series_energy()`

### Dashboard

- [x] Las entidades del dashboard se resuelven por **`unique_id`**, no por
      id construido: el id de una entidad depende del nombre traducido y
      cambiaba con las traducciones

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

## Hecho en la iteración anterior (2026-10-21)

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
- [x] **Backfill del recorder**: se implementó, se descartó y **volvió**,
      con la semántica correcta (el valor acumulado del contador, en la
      escala del recorder). Ver la iteración de 2026-10-22.
- [x] Panel de Energía configurado con el agregado, validado sin errores

- [x] **Pestañas por planta** (`scripts/create_plant_dashboard.py`): una
      sola página "Felicity Solar" con una pestaña por planta, cada una con
      su gráfico de generación
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

- [x] **Historial real** (`scripts/backfill_history.py`): el endpoint
      `/storageRealtimeData/chart_storageRealtimeData_mate` devuelve la serie
      de 5 minutos por planta en W. La alineación se resolvió midiendo la
      cadencia (3 muestras en 13 min = 5 min) y usando el tramo nocturno
      (puesta de sol 20:55 → salida 07:05). Se verifica contra el contador
      diario del API antes de escribir nada: desviación del 1-2 %
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
| D6 | El API solo publica **4 días** de serie de potencias: el histórico de batería y red del panel empieza ahí, no en el inicio de la planta | Medio, limite del fabricante |
| D7 | La energía de la batería se integra con la potencia del flujo (el API publica su contador diario vacío): tiene un error de integración del orden del 1 % | Bajo, documentado |

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
