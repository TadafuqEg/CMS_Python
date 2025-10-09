import asyncio
import logging
from datetime import datetime
import ssl
import websockets
from typing import Dict, Set
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call_result
from ocpp.v16.enums import (
    Action,
    RegistrationStatus,
    AuthorizationStatus,
    RemoteStartStopStatus,
    AvailabilityStatus,
    ConfigurationStatus,
    ClearCacheStatus,
    DataTransferStatus,
    ResetStatus,
    DiagnosticsStatus,
    FirmwareStatus,
    ReservationStatus,
    ChargingProfileStatus,
    TriggerMessageStatus,
    MessageTrigger
)

logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for detailed logging

# Global client manager to track all connected clients
class ClientManager:
    def __init__(self):
        self.clients: Dict[str, 'CentralSystem'] = {}
        self.master_connections: Set[websockets.WebSocketServerProtocol] = set()
        
    def add_client(self, client_id: str, central_system: 'CentralSystem'):
        """Add a new client to the manager"""
        self.clients[client_id] = central_system
        logging.info(f"Client {client_id} added. Total clients: {len(self.clients)}")
        
    def remove_client(self, client_id: str):
        """Remove a client from the manager"""
        if client_id in self.clients:
            del self.clients[client_id]
            logging.info(f"Client {client_id} removed. Total clients: {len(self.clients)}")
            
    def add_master_connection(self, websocket: websockets.WebSocketServerProtocol):
        """Add a master connection for broadcasting"""
        self.master_connections.add(websocket)
        logging.info(f"Master connection added. Total master connections: {len(self.master_connections)}")
        
    def remove_master_connection(self, websocket: websockets.WebSocketServerProtocol):
        """Remove a master connection"""
        self.master_connections.discard(websocket)
        logging.info(f"Master connection removed. Total master connections: {len(self.master_connections)}")
        
    async def broadcast_to_all_clients(self, message: str):
        """Broadcast a message to all connected clients"""
        if not self.clients:
            logging.warning("No clients connected to broadcast to")
            return
            
        tasks = []
        disconnected_clients = []
        
        for client_id, central_system in self.clients.items():
            try:
                if hasattr(central_system, 'websocket') and not central_system.websocket.closed:
                    tasks.append(central_system.websocket.send(message))
                else:
                    disconnected_clients.append(client_id)
            except Exception as e:
                logging.error(f"Error preparing broadcast for client {client_id}: {e}")
                disconnected_clients.append(client_id)
                
        # Remove disconnected clients
        for client_id in disconnected_clients:
            self.remove_client(client_id)
            
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
                logging.info(f"Broadcasted message to {len(tasks)} clients")
            except Exception as e:
                logging.error(f"Error broadcasting message: {e}")
                
    async def handle_master_connection(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Handle master connections for broadcasting"""
        self.add_master_connection(websocket)
        
        try:
            async for message in websocket:
                logging.info(f"Master connection received message: {message}")
                # Broadcast the message to all clients
                await self.broadcast_to_all_clients(message)
                
        except websockets.exceptions.ConnectionClosed:
            logging.info("Master connection closed")
        except Exception as e:
            logging.error(f"Error handling master connection: {e}")
        finally:
            self.remove_master_connection(websocket)

# Global client manager instance
client_manager = ClientManager()

class CentralSystem(cp):
    def __init__(self, charge_point_id: str, websocket: websockets.WebSocketServerProtocol, *args, **kwargs):
        super().__init__(charge_point_id, websocket, *args, **kwargs)
        self.charge_point_id = charge_point_id
        self.websocket = websocket
        self.transaction_counter = 0  # Initialize transaction counter
        logging.debug("CentralSystem initialized with route_map: %s", self.route_map)
        
        # Register this client with the global manager
        client_manager.add_client(charge_point_id, self)
        
    async def start(self):
        """Override start method to handle cleanup"""
        try:
            await super().start()
        finally:
            # Remove client from manager when connection closes
            client_manager.remove_client(self.charge_point_id)

    @on(Action.authorize)
    async def on_authorize(self, id_tag, **kwargs):
        try:
            logging.info(f"Received Authorize: id_tag {id_tag}")
            return call_result.Authorize(
                id_tag_info={'status': AuthorizationStatus.accepted}
            )
        except Exception as e:
            logging.error(f"Error in on_authorize: {e}")
            raise

    @on(Action.boot_notification)
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, firmware_version, **kwargs):
        try:
            logging.info(f"Received BootNotification from {charge_point_model}, {charge_point_vendor}, firmware: {firmware_version}")
            return call_result.BootNotification(
                current_time=datetime.utcnow().isoformat(),
                interval=60,
                status=RegistrationStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_boot_notification: {e}")
            raise

    @on(Action.cancel_reservation)
    async def on_cancel_reservation(self, reservation_id, **kwargs):
        try:
            logging.info(f"Received CancelReservation: reservation_id {reservation_id}")
            return call_result.CancelReservation(
                status=ReservationStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_cancel_reservation: {e}")
            raise

    @on(Action.change_availability)
    async def on_change_availability(self, connector_id, type, **kwargs):
        try:
            logging.info(f"Received ChangeAvailability: connector_id {connector_id}, type {type}")
            return call_result.ChangeAvailability(
                status=AvailabilityStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_change_availability: {e}")
            raise

    @on(Action.change_configuration)
    async def on_change_configuration(self, key, value, **kwargs):
        try:
            logging.info(f"Received ChangeConfiguration: key {key}, value {value}")
            return call_result.ChangeConfiguration(
                status=ConfigurationStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_change_configuration: {e}")
            raise

    @on(Action.clear_cache)
    async def on_clear_cache(self, **kwargs):
        try:
            logging.info("Received ClearCache")
            return call_result.ClearCache(
                status=ClearCacheStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_clear_cache: {e}")
            raise

    @on(Action.clear_charging_profile)
    async def on_clear_charging_profile(self, id=None, connector_id=None, charging_profile_purpose=None, stack_level=None, **kwargs):
        try:
            logging.info(f"Received ClearChargingProfile: id {id}, connector_id {connector_id}, purpose {charging_profile_purpose}, stack_level {stack_level}")
            return call_result.ClearChargingProfile(
                status=ChargingProfileStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_clear_charging_profile: {e}")
            raise

    @on(Action.data_transfer)
    async def on_data_transfer(self, vendor_id, message_id=None, data=None, **kwargs):
        try:
            logging.info(f"Received DataTransfer: vendor_id {vendor_id}, message_id {message_id}, data {data}")
            return call_result.DataTransfer(
                status=DataTransferStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_data_transfer: {e}")
            raise

    @on(Action.diagnostics_status_notification)
    async def on_diagnostics_status_notification(self, status, **kwargs):
        try:
            logging.info(f"Received DiagnosticsStatusNotification: status {status}")
            return call_result.DiagnosticsStatusNotification()
        except Exception as e:
            logging.error(f"Error in on_diagnostics_status_notification: {e}")
            raise

    @on(Action.firmware_status_notification)
    async def on_firmware_status_notification(self, status, **kwargs):
        try:
            logging.info(f"Received FirmwareStatusNotification: status {status}")
            return call_result.FirmwareStatusNotification()
        except Exception as e:
            logging.error(f"Error in on_firmware_status_notification: {e}")
            raise

    @on(Action.get_configuration)
    async def on_get_configuration(self, key=None, **kwargs):
        try:
            logging.info(f"Received GetConfiguration: key {key}")
            configuration_key = [{"key": "example_key", "value": "example_value"}] if not key else []
            return call_result.GetConfiguration(
                configuration_key=configuration_key
            )
        except Exception as e:
            logging.error(f"Error in on_get_configuration: {e}")
            raise

    @on(Action.get_diagnostics)
    async def on_get_diagnostics(self, location, start_time=None, stop_time=None, retries=None, retry_interval=None, **kwargs):
        try:
            logging.info(f"Received GetDiagnostics: location {location}, start_time {start_time}, stop_time {stop_time}")
            return call_result.GetDiagnostics(
                file_name="diagnostics.log"
            )
        except Exception as e:
            logging.error(f"Error in on_get_diagnostics: {e}")
            raise

    @on(Action.get_local_list_version)
    async def on_get_local_list_version(self, **kwargs):
        try:
            logging.info("Received GetLocalListVersion")
            return call_result.GetLocalListVersion(
                list_version=1
            )
        except Exception as e:
            logging.error(f"Error in on_get_local_list_version: {e}")
            raise

    @on(Action.heartbeat)
    async def on_heartbeat(self, **kwargs):
        try:
            logging.info("Received Heartbeat")
            return call_result.Heartbeat(
                current_time=datetime.utcnow().isoformat()
            )
        except Exception as e:
            logging.error(f"Error in on_heartbeat: {e}")
            raise

    @on(Action.meter_values)
    async def on_meter_values(self, connector_id, transaction_id, meter_value, **kwargs):
        try:
            logging.info(f"Received MeterValues: connector_id {connector_id}, transaction_id {transaction_id}")
            return call_result.MeterValues()
        except Exception as e:
            logging.error(f"Error in on_meter_values: {e}")
            raise

    @on(Action.remote_start_transaction)
    async def on_remote_start_transaction(self, id_tag, connector_id=None, **kwargs):
        try:
            logging.info(f"Received RemoteStartTransaction: id_tag {id_tag}, connector_id {connector_id}")
            return call_result.RemoteStartTransaction(
                status=RemoteStartStopStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_remote_start_transaction: {e}")
            raise

    @on(Action.remote_stop_transaction)
    async def on_remote_stop_transaction(self, transaction_id, **kwargs):
        try:
            logging.info(f"Received RemoteStopTransaction: transaction_id {transaction_id}")
            return call_result.RemoteStopTransaction(
                status=RemoteStartStopStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_remote_stop_transaction: {e}")
            raise

    @on(Action.reserve_now)
    async def on_reserve_now(self, connector_id, expiry_date, id_tag, reservation_id, parent_id_tag=None, **kwargs):
        try:
            logging.info(f"Received ReserveNow: connector_id {connector_id}, reservation_id {reservation_id}, id_tag {id_tag}")
            return call_result.ReserveNow(
                status=ReservationStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_reserve_now: {e}")
            raise

    @on(Action.reset)
    async def on_reset(self, type, **kwargs):
        try:
            logging.info(f"Received Reset: type {type}")
            return call_result.Reset(
                status=ResetStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_reset: {e}")
            raise

    @on(Action.send_local_list)
    async def on_send_local_list(self, list_version, update_type, local_authorization_list=None, **kwargs):
        try:
            logging.info(f"Received SendLocalList: list_version {list_version}, update_type {update_type}")
            return call_result.SendLocalList(
                status=DataTransferStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_send_local_list: {e}")
            raise

    @on(Action.set_charging_profile)
    async def on_set_charging_profile(self, connector_id, cs_charging_profiles, **kwargs):
        try:
            logging.info(f"Received SetChargingProfile: connector_id {connector_id}, profiles {cs_charging_profiles}")
            return call_result.SetChargingProfile(
                status=ChargingProfileStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_set_charging_profile: {e}")
            raise

    @on(Action.start_transaction)
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        try:
            self.transaction_counter += 1  # Increment transaction counter
            logging.info(f"Received StartTransaction: connector_id {connector_id}, id_tag {id_tag}, transaction_id {self.transaction_counter}")
            return call_result.StartTransaction(
                transaction_id=self.transaction_counter,
                id_tag_info={'status': AuthorizationStatus.accepted}
            )
        except Exception as e:
            logging.error(f"Error in on_start_transaction: {e}")
            raise

    @on(Action.status_notification)
    async def on_status_notification(self, connector_id, error_code, status, **kwargs):
        try:
            logging.info(f"Received StatusNotification: connector_id {connector_id}, status {status}, error_code {error_code}")
            return call_result.StatusNotification()
        except Exception as e:
            logging.error(f"Error in on_status_notification: {e}")
            raise

    @on(Action.stop_transaction)
    async def on_stop_transaction(self, transaction_id, id_tag, meter_stop, timestamp, **kwargs):
        try:
            logging.info(f"Received StopTransaction: transaction_id {transaction_id}, id_tag {id_tag}")
            return call_result.StopTransaction(
                id_tag_info={'status': AuthorizationStatus.accepted}
            )
        except Exception as e:
            logging.error(f"Error in on_stop_transaction: {e}")
            raise

    @on(Action.trigger_message)
    async def on_trigger_message(self, requested_message, connector_id=None, **kwargs):
        try:
            logging.info(f"Received TriggerMessage: requested_message {requested_message}, connector_id {connector_id}")
            return call_result.TriggerMessage(
                status=TriggerMessageStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_trigger_message: {e}")
            raise

    @on(Action.unlock_connector)
    async def on_unlock_connector(self, connector_id, **kwargs):
        try:
            logging.info(f"Received UnlockConnector: connector_id {connector_id}")
            return call_result.UnlockConnector(
                status='Unlocked'
            )
        except Exception as e:
            logging.error(f"Error in on_unlock_connector: {e}")
            raise

    @on(Action.update_firmware)
    async def on_update_firmware(self, location, retrieve_date, retries=None, retry_interval=None, **kwargs):
        try:
            logging.info(f"Received UpdateFirmware: location {location}, retrieve_date {retrieve_date}")
            return call_result.UpdateFirmware()
        except Exception as e:
            logging.error(f"Error in on_update_firmware: {e}")
            raise

async def handle_client_connection(websocket, path):
    """Handle regular client connections"""
    charge_point_id = path.split('/')[-1]
    logging.info(f"Client connecting: {charge_point_id}")
    
    central_system = CentralSystem(charge_point_id, websocket)
    await central_system.start()

async def main():
    try:
        # Create an SSL context for WSS
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")  # Update paths if needed

        # Start server with both client and master connection handlers
        async with websockets.serve(
            lambda ws, path: (
                client_manager.handle_master_connection(ws, path) 
                if path.startswith('/master') 
                else handle_client_connection(ws, path)
            ),
            "localhost",
            9000,
            subprotocols=["ocpp1.6"],
            ssl=ssl_context  # Add SSL context for WSS
        ):
            logging.info("OCPP 1.6 server running on wss://localhost:9000")
            logging.info("Regular clients connect to: wss://localhost:9000/{charge_point_id}")
            logging.info("Master connections connect to: wss://localhost:9000/master")
            await asyncio.Future()  # Run forever
    except Exception as e:
        logging.error(f"Server failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())