import asyncio
import json
import logging
import ssl
import websockets

logging.basicConfig(level=logging.INFO)

async def test_universal_client():
    """Test client that connects to the universal websocket on port 9001"""
    
    try:
        # SSL context for secure connection
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(
            "wss://localhost:9001",
            subprotocols=["ocpp1.6"],
            ssl=ssl_context
        ) as ws:
            logging.info("Connected to universal websocket on port 9001")
            
            # Send a test message
            test_message = json.dumps({
                "messageType": "test",
                "data": "Hello from universal client!",
                "timestamp": "2024-01-01T00:00:00Z"
            })
            
            await ws.send(test_message)
            logging.info(f"Sent test message: {test_message}")
            
            # Listen for responses
            try:
                async for message in ws:
                    logging.info(f"Received response: {message}")
            except websockets.exceptions.ConnectionClosed:
                logging.info("Connection closed")
                
    except Exception as e:
        logging.error(f"Test client error: {e}")

async def test_target_client():
    """Test client that connects to the target websocket on port 9000"""
    
    try:
        # SSL context for secure connection
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(
            "wss://localhost:9000/test_cp",
            subprotocols=["ocpp1.6"],
            ssl=ssl_context
        ) as ws:
            logging.info("Connected to target websocket on port 9000")
            
            # Listen for messages
            try:
                async for message in ws:
                    logging.info(f"Received message on target: {message}")
            except websockets.exceptions.ConnectionClosed:
                logging.info("Target connection closed")
                
    except Exception as e:
        logging.error(f"Target client error: {e}")

async def main():
    """Run both test clients"""
    logging.info("Starting test clients...")
    
    # Run both clients concurrently
    await asyncio.gather(
        test_universal_client(),
        test_target_client(),
        return_exceptions=True
    )

if __name__ == "__main__":
    asyncio.run(main())
