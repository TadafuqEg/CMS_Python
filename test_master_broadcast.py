import asyncio
import json
import logging
import ssl
import websockets

logging.basicConfig(level=logging.INFO)

async def master_client():
    """Master client that can broadcast messages to all connected clients"""
    
    try:
        # SSL context for secure connection
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(
            "wss://localhost:9000/master",
            subprotocols=["ocpp1.6"],
            ssl=ssl_context
        ) as ws:
            logging.info("Master client connected to wss://localhost:9000/master")
            
            # Send a broadcast message
            broadcast_message = json.dumps({
                "messageType": "broadcast",
                "action": "system_notification",
                "data": "System maintenance scheduled for tonight",
                "timestamp": "2024-01-01T00:00:00Z"
            })
            
            await ws.send(broadcast_message)
            logging.info(f"Sent broadcast message: {broadcast_message}")
            
            # Listen for responses
            try:
                async for message in ws:
                    logging.info(f"Received response: {message}")
            except websockets.exceptions.ConnectionClosed:
                logging.info("Master connection closed")
                
    except Exception as e:
        logging.error(f"Master client error: {e}")

async def regular_client(client_id="test_cp"):
    """Regular client that connects to the central system"""
    
    try:
        # SSL context for secure connection
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(
            f"wss://localhost:9000/{client_id}",
            subprotocols=["ocpp1.6"],
            ssl=ssl_context
        ) as ws:
            logging.info(f"Regular client {client_id} connected to wss://localhost:9000/{client_id}")
            
            # Send a boot notification
            boot_message = json.dumps([
                2,
                "unique-id",
                "BootNotification",
                {
                    "chargePointModel": "Test Model",
                    "chargePointVendor": "Test Vendor",
                    "firmwareVersion": "1.0.0"
                }
            ])
            
            await ws.send(boot_message)
            logging.info(f"Sent boot notification: {boot_message}")
            
            # Listen for messages (including broadcasts)
            try:
                async for message in ws:
                    logging.info(f"Client {client_id} received: {message}")
            except websockets.exceptions.ConnectionClosed:
                logging.info(f"Client {client_id} connection closed")
                
    except Exception as e:
        logging.error(f"Regular client {client_id} error: {e}")

async def main():
    """Run both master and regular clients"""
    logging.info("Starting test clients...")
    
    # Run multiple clients concurrently
    await asyncio.gather(
        master_client(),
        regular_client("cp1"),
        regular_client("cp2"),
        regular_client("cp3"),
        return_exceptions=True
    )

if __name__ == "__main__":
    asyncio.run(main())
