import asyncio
import logging
import ssl
import websockets
from datetime import datetime
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call
from ocpp.v16.enums import RegistrationStatus

logging.basicConfig(level=logging.DEBUG)

class ChargePointClient(cp):
    async def send_boot_notification(self):
        request = call.BootNotification(
            charge_point_model="ModelX",
            charge_point_vendor="VendorY",
            firmware_version="1.0"
        )
        logging.info(f"Sending BootNotification: {request}")
        response = await self.call(request)
        logging.info(f"BootNotification response: {response.status}")
        return response

    async def send_heartbeat(self):
        request = call.Heartbeat()
        logging.info(f"Sending Heartbeat: {request}")
        response = await self.call(request)
        logging.info(f"Heartbeat response: {response.current_time}")
        return response

async def main():
    try:
        # Disable SSL verification for ngrok's certificate
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        logging.info("Attempting to connect to wss://celeste-supersacral-overmilitaristically.ngrok-free.app/cp1")
        async with websockets.connect(
            "wss://celeste-supersacral-overmilitaristically.ngrok-free.app/cp1",
            subprotocols=["ocpp1.6"],
            ssl=ssl_context
        ) as ws:
            logging.info("WebSocket connection established")
            cp = ChargePointClient("cp1", ws)
            await cp.start()
            await cp.send_boot_notification()
            await cp.send_heartbeat()
            await asyncio.sleep(10)
    except Exception as e:
        logging.error(f"Client error: {e}")

if __name__ == "__main__":
    asyncio.run(main())