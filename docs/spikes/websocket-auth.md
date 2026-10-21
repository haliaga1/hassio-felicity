# Spike: autenticación del WebSocket

> **Pregunta abierta Q1** de `SPECS.md`.
> **Estado: CERRADA** — 2026-10-21, con una cuenta real (2 plantas, 2×
> IVEM8048-II + 2× FLA48100-EU).

## Veredicto

**El WebSocket no es un transporte utilizable para este equipo.**

| Comprobación | Resultado |
|---|---|
| Handshake en `wss://shine-api.felicitysolar.com/socket/energy-flow/{sn}` | ✅ Handshake correcto |
| Token `Authorization` en el handshake | ✅ **Aceptado**: sin él, el gateway redirige a `/token_expiration` |
| Path sin el prefijo `/socket` | ❌ `404 Invalid response status` |
| Frames recibidos tras 75 s, socket de **dispositivo** | **0** |
| Frames recibidos tras 75 s, socket de **planta** (`energy-plant-flow/{plantId}`) | **0** |
| Formatos de suscripción probados | 4 (`plant:false`+collector, sin `plant`, `plant:true`, mínimo) |
| Cabeceras REST añadidas (`lang`, `source`, `Node`) | Sin efecto |

## Lo que sí se aprendió

1. **La URL base es `wss://shine-api.felicitysolar.com/socket`**, no
   `wss://shine-api.felicitysolar.com`. Sin el prefijo `/socket` el
   handshake responde 404, que es un error confuso.
2. **El token se acepta en el handshake.** La web oficial reutiliza la
   cookie del navegador, pero el gateway **también** valida la cabecera
   `Authorization`: sin ella, redirige a `/token_expiration` igual que hace
   con las peticiones REST.
3. **La conexión se establece pero el servidor no empuja datos** para esta
   combinación de inversor y colector. La propia web oficial contempla
   esta situación: su vista de flujo comprueba el flag `connectWebsocket`
   por dispositivo y, si no está, **cae a sondeo por polling**.

## Consecuencia para el diseño

> **El sondeo REST es el camino garantizado. El WebSocket es una mejora
> opcional, nunca la única fuente.**

Esto es exactamente lo que hace el coordinator:

- el sondeo REST corre **siempre**, cada 60 s por defecto;
- el WebSocket corre **en paralelo** y, si algún día el fabricante lo
  habilita para este equipo, sus snapshots se fusionan sin cambiar nada
  más;
- si el socket no entrega nada, no pasa nada: el coordinator no depende
  de él.

El cliente no insiste: tras 10 intentos de reconexión con backoff
exponencial, la tarea del WebSocket termina y solo queda el polling.

## Reproducirlo

```bash
export FELICITY_TEST_EMAIL="..."
export FELICITY_TEST_PASSWORD="..."
uv run python scripts/spike_websocket_auth.py
```

El script prueba el handshake **con** y **sin** token, envía el comando de
suscripción y espera 12 s a ver si llega un snapshot.

## Nota para el futuro

Si alguien con un equipo **más nuevo** (un colector con push habilitado)
reporta que sí recibe frames, la implementación ya está lista: basta con
que el handshake acepte el token, que ya se verificó que lo hace. El
único cambio sería confirmar el prefijo `/socket` para ese nodo.
