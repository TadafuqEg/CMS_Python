import asyncio
import json
import logging
import ssl
import websockets

logging.basicConfig(level=logging.DEBUG)

CENTRAL_SYSTEM_URL = "wss://localhost:9000"  # Main OCPP backend
INTERCEPTOR_PORT = 9100                      # New port for chargers


async def interceptor_handler(websocket, path):
    """Intercept messages between Charging Station and Central System."""
    charge_point_id = path.split("/")[-1]
    logging.info(f"⚡ Charger connected: {charge_point_id}")

    # ---- SSL setup for connecting to CentralSystem (client mode) ----
    ssl_client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_client_context.load_verify_locations("cert.pem")
    ssl_client_context.check_hostname = False  # disable hostname check for localhost
    ssl_client_context.verify_mode = ssl.CERT_NONE  # skip verification (local use only)

    try:
        # Connect to the real Central System server securely
        async with websockets.connect(
            f"{CENTRAL_SYSTEM_URL}/{charge_point_id}",
            subprotocols=["ocpp1.6"],
            ssl=ssl_client_context
        ) as central_ws:
            logging.info(f"🔗 Connected securely to Central System for {charge_point_id}")

            async def forward_to_central():
                async for message in websocket:
                    logging.debug(f"➡️ From Charger → Central: {message}")
                    await central_ws.send(message)

            async def forward_to_charger():
                async for message in central_ws:
                    logging.debug(f"⬅️ From Central → Charger: {message}")
                    await websocket.send(message)

            await asyncio.gather(forward_to_central(), forward_to_charger())

    except Exception as e:
        logging.error(f"❌ Interceptor error for {charge_point_id}: {e}")


async def main():
    try:
        # ---- SSL setup for accepting connections from charger (server mode) ----
        ssl_server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_server_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")

        async with websockets.serve(
            interceptor_handler,
            "localhost",
            INTERCEPTOR_PORT,
            subprotocols=["ocpp1.6"],
            ssl=ssl_server_context
        ):
            logging.info(f"🚦 Interceptor listening securely on wss://localhost:{INTERCEPTOR_PORT}")
            await asyncio.Future()
    except Exception as e:
        logging.error(f"❌ Failed to start interceptor: {e}")


if __name__ == "__main__":
    asyncio.run(main())
