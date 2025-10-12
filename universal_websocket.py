import asyncio
import json
import logging
import ssl
import websockets
from typing import Set, Dict

logging.basicConfig(level=logging.DEBUG)

# Configuration
UNIVERSAL_PORT = 9001
TARGET_PORT = 9000
TARGET_HOST = "localhost"

class UniversalWebSocketServer:
    def __init__(self):
        self.universal_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.target_connection = None
        
    async def register_universal_client(self, websocket):
        """Register a new universal client connection"""
        self.universal_clients.add(websocket)
        logging.info(f"Universal client connected. Total universal clients: {len(self.universal_clients)}")
        
    async def unregister_universal_client(self, websocket):
        """Unregister a universal client connection"""
        self.universal_clients.discard(websocket)
        logging.info(f"Universal client disconnected. Total universal clients: {len(self.universal_clients)}")
        
    async def ensure_target_connection(self):
        """Ensure we have a connection to the target server"""
        if self.target_connection is None or self.target_connection.closed:
            try:
                # SSL context for connecting to target server
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                target_url = f"wss://{TARGET_HOST}:{TARGET_PORT}/universal_broadcaster"
                logging.info(f"Connecting to target server: {target_url}")
                
                self.target_connection = await websockets.connect(
                    target_url,
                    subprotocols=["ocpp1.6"],
                    ssl=ssl_context
                )
                logging.info("Connected to target server")
                
                # Start listening for responses from target server
                asyncio.create_task(self.listen_to_target())
                
            except Exception as e:
                logging.error(f"Error connecting to target server: {e}")
                self.target_connection = None
                
    async def listen_to_target(self):
        """Listen for messages from the target server and forward to universal clients"""
        try:
            async for message in self.target_connection:
                logging.info(f"Received message from target server: {message}")
                await self.broadcast_to_universal_clients(message)
        except websockets.exceptions.ConnectionClosed:
            logging.info("Target connection closed")
            self.target_connection = None
        except Exception as e:
            logging.error(f"Error listening to target: {e}")
            self.target_connection = None
            
    async def broadcast_to_universal_clients(self, message):
        """Broadcast message to all universal clients"""
        if not self.universal_clients:
            return
            
        tasks = []
        disconnected_clients = []
        
        for client in self.universal_clients.copy():
            try:
                tasks.append(client.send(message))
            except websockets.exceptions.ConnectionClosed:
                disconnected_clients.append(client)
            except Exception as e:
                logging.error(f"Error sending to universal client: {e}")
                disconnected_clients.append(client)
                
        # Remove disconnected clients
        for client in disconnected_clients:
            self.universal_clients.discard(client)
            
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
                logging.info(f"Broadcasted message to {len(tasks)} universal clients")
            except Exception as e:
                logging.error(f"Error broadcasting to universal clients: {e}")
                
    async def send_to_target(self, message):
        """Send message to the target server"""
        await self.ensure_target_connection()
        
        if self.target_connection and not self.target_connection.closed:
            try:
                await self.target_connection.send(message)
                logging.info(f"Sent message to target server: {message}")
            except Exception as e:
                logging.error(f"Error sending to target server: {e}")
                self.target_connection = None
        else:
            logging.warning("No connection to target server available")
                
    async def handle_universal_client(self, websocket, path):
        """Handle connections to the universal websocket server"""
        await self.register_universal_client(websocket)
        
        try:
            async for message in websocket:
                logging.info(f"Received message from universal client: {message}")
                
                # Send the message to the target server (port 9000)
                await self.send_to_target(message)
                
        except websockets.exceptions.ConnectionClosed:
            logging.info("Universal client disconnected")
        except Exception as e:
            logging.error(f"Error handling universal client: {e}")
        finally:
            await self.unregister_universal_client(websocket)

async def main():
    server = UniversalWebSocketServer()
    
    try:
        # Create SSL context for secure WebSocket (WSS)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
        
        # Start the universal websocket server with SSL
        async with websockets.serve(
            server.handle_universal_client,
            "localhost",
            UNIVERSAL_PORT,
            subprotocols=["ocpp1.6"],
            ssl=ssl_context
        ):
            logging.info(f"Universal WebSocket server running on wss://localhost:{UNIVERSAL_PORT}")
            logging.info(f"Messages will be forwarded to wss://localhost:{TARGET_PORT}")
            
            # Keep the server running
            await asyncio.Future()
            
    except Exception as e:
        logging.error(f"Failed to start universal websocket server: {e}")

if __name__ == "__main__":
    asyncio.run(main())
