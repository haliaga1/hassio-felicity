# Spike: autenticación del WebSocket

> **Pregunta abierta Q1** de `SPECS.md`.
> **Estado:** abierta — requiere una cuenta real.

## Qué hay que determinar

La web oficial abre el WebSocket con la **cookie de sesión del navegador**.
Un cliente de servidor no tiene esa cookie. La pregunta es si el gateway
acepta el handshake con la **cabecera `Authorization`** y nada más.

## Por qué importa

| Resultado | Consecuencia |
|---|---|
| **Aceptado** | El WebSocket es el transporte primario: datos en tiempo real sin polling. |
| **Rechazado** | El tiempo real depende del polling REST (60 s por defecto) y el WebSocket queda como mejora opcional. |

## Qué hace el cliente hoy

`felicity_client/realtime.py` envía la cabecera `Authorization` en el
handshake cuando hay un token disponible:

```python
async def _handshake_headers(self) -> dict[str, str]:
    if self._token_provider is None:
        return {}
    try:
        token = await self._token_provider()
    except Exception:
        return {}
    return {"Authorization": token} if token else {}
```

Si el token no se puede obtener, el handshake se intenta **sin** cabeceras y
la conexión se cierra — nunca se envía un token vacío.

## Cómo reproducirlo

```bash
export FELICITY_TEST_EMAIL="..."
export FELICITY_TEST_PASSWORD="..."
uv run python scripts/spike_websocket_auth.py
```

El script:

1. hace login y obtiene el token;
2. intenta el handshake **con** `Authorization`;
3. intenta el handshake **sin** cabeceras;
4. en cada caso envía el comando de suscripción y espera 10 s a ver si llega
   un snapshot;
5. imprime un veredicto.

## Criterio de éxito

El spike está cerrado cuando el script se ha ejecutado contra una cuenta
real y su salida está pegada en este documento.

## Impacto en el diseño

Ninguno: el `RealtimeService` ya degrada a polling REST si el socket no
funciona, y el coordinator arranca una tarea por dispositivo. Este spike
solo determina si el tiempo real es el camino por defecto o la excepción.
