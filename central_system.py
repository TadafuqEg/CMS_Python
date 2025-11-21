import asyncio
import logging
from datetime import datetime
import ssl
import websockets
import json
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
    MessageTrigger,
    GetCompositeScheduleStatus, 
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ClientManager:
    """Manages connected clients and master connections"""
    def __init__(self):
        self.clients = {}
        self.master_connections = []
    
    def add_client(self, charge_point_id, central_system):
        """Add a client to the manager"""
        self.clients[charge_point_id] = central_system
        logging.info(f"Client {charge_point_id} added. Total clients: {len(self.clients)}")
    
    def remove_client(self, charge_point_id):
        """Remove a client from the manager"""
        if charge_point_id in self.clients:
            del self.clients[charge_point_id]
            logging.info(f"Client {charge_point_id} removed. Total clients: {len(self.clients)}")
    
    async def broadcast_to_all_clients(self, message):
        """Broadcast a message to all connected clients"""
        if not self.clients:
            logging.warning("No clients connected to broadcast to")
            return False
        
        success_count = 0
        tasks = []
        
        for charge_point_id, client in self.clients.items():
            try:
                # Create task for sending message to client
                task = asyncio.create_task(client.send(message))
                tasks.append((charge_point_id, task))
            except Exception as e:
                logging.error(f"Failed to create send task for {charge_point_id}: {e}")
        
        # Wait for all send operations to complete
        for charge_point_id, task in tasks:
            try:
                success = await task
                if success:
                    success_count += 1
            except Exception as e:
                logging.error(f"Failed to send message to {charge_point_id}: {e}")
        
        logging.info(f"Broadcasted message to {success_count}/{len(self.clients)} clients")
        return success_count > 0
    
    async def handle_master_connection(self, websocket, path):
        """Handle master socket connections"""
        logging.info("Master connection added. Total master connections: 1")
        self.master_connections.append(websocket)
        
        try:
            async for message in websocket:
                logging.info(f"Master socket received: {message}")
                
                # Broadcast to all clients
                success = await self.broadcast_to_all_clients(message)
                
                # Send feedback to master
                if success:
                    feedback = {"status": "success", "message": "Message broadcasted successfully"}
                else:
                    feedback = {"status": "warning", "message": "No clients connected"}
                
                await websocket.send(json.dumps(feedback))
                
        except websockets.exceptions.ConnectionClosed:
            logging.info("Master connection closed")
        finally:
            if websocket in self.master_connections:
                self.master_connections.remove(websocket)

    async def broadcast_to_master(self, message):
        """Broadcast a message to the master connection"""
        if not self.master_connections:
            # logging.debug("No master connection to broadcast to")
            return False
        
        success_count = 0
        message_str = json.dumps(message) if isinstance(message, dict) else message
        
        for websocket in self.master_connections:
            try:
                await websocket.send(message_str)
                success_count += 1
            except Exception as e:
                logging.error(f"Failed to send to master: {e}")
                
        return success_count > 0

# Global client manager instance
client_manager = ClientManager()

class CentralSystem(cp):
    def __init__(self, charge_point_id, websocket, *args, **kwargs):
        super().__init__(charge_point_id, websocket, *args, **kwargs)
        self.charge_point_id = charge_point_id
        self.websocket = websocket
        self.transaction_counter = 0  # Initialize transaction counter
        
        # Register this client with the global manager
        client_manager.add_client(charge_point_id, self)
        
    async def send(self, message):
        """Send a message to the charge point"""
        try:
            if hasattr(self.websocket, 'send'):
                await self.websocket.send(message)
                logging.info(f"Sent message to {self.charge_point_id}: {message}")
                return True
            else:
                logging.error(f"Cannot send message to {self.charge_point_id}: websocket has no send method")
                return False
        except Exception as e:
            logging.error(f"Failed to send message to {self.charge_point_id}: {e}")
            return False

    async def start(self):
        """Override start method to handle cleanup and malformed messages"""
        try:
            await super().start()
        except Exception as e:
            # Check if it's a FormatViolationError from malformed JSON
            if "FormatViolationError" in str(e) or "Message is not valid JSON" in str(e):
                logging.warning(f"Received malformed message from {self.charge_point_id}: {e}")
                logging.warning("Continuing to handle other messages...")
                # Don't re-raise the error, just log it and continue
                return
            else:
                # Re-raise other errors
                raise
        finally:
            # Remove client from manager when connection closes
            client_manager.remove_client(self.charge_point_id)

    @on(Action.Authorize)
    async def on_authorize(self, id_tag, **kwargs):
        try:
            logging.info(f"Received Authorize: id_tag {id_tag}")
            return call_result.AuthorizePayload(
                id_tag_info={'status': AuthorizationStatus.accepted}
            )
        except Exception as e:
            logging.error(f"Error in on_authorize: {e}")
            raise

    @on(Action.BootNotification)
    async def on_boot_notification(self, charge_point_model, charge_point_vendor, firmware_version, **kwargs):
        try:
            logging.info(f"Received BootNotification from {charge_point_model}, {charge_point_vendor}, firmware: {firmware_version}")
            
            # Forward to master
            await client_manager.broadcast_to_master({
                "message_type": "ocpp_forward",
                "charger_id": self.charge_point_id,
                "direction": "incoming",
                "ocpp_message": [2, "boot", "BootNotification", {
                    "chargePointModel": charge_point_model,
                    "chargePointVendor": charge_point_vendor,
                    "firmwareVersion": firmware_version,
                    **kwargs
                }]
            })

            # Save BootNotification data to database
            await self.save_boot_notification_to_db(charge_point_model, charge_point_vendor, firmware_version, kwargs)
            
            return call_result.BootNotificationPayload(
                current_time=datetime.now().isoformat(),
                interval=60,
                status=RegistrationStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_boot_notification: {e}")
            raise

    async def save_boot_notification_to_db(self, charge_point_model, charge_point_vendor, firmware_version, kwargs):
        """Save BootNotification data to database"""
        try:
            from app.models.database import SessionLocal, Charger
            from datetime import datetime
            
            db = SessionLocal()
            try:
                charger = db.query(Charger).filter(Charger.id == self.charge_point_id).first()
                if not charger:
                    logging.warning(f"Charger {self.charge_point_id} not found in database during BootNotification")
                    charger = Charger(id=self.charge_point_id)
                    db.add(charger)
                
                # Update charger with BootNotification data
                charger.vendor = charge_point_vendor
                charger.model = charge_point_model
                charger.firmware_version = firmware_version
                charger.status = "Available"
                charger.last_heartbeat = datetime.utcnow()
                charger.connection_time = datetime.utcnow()
                charger.is_connected = True
                
                # Save all BootNotification data in configuration
                if not charger.configuration:
                    charger.configuration = {}
                
                # Store all BootNotification data
                charger.configuration.update({
                    "boot_notification_data": {
                        "chargePointModel": charge_point_model,
                        "chargePointVendor": charge_point_vendor,
                        "firmwareVersion": firmware_version,
                        **kwargs
                    },
                    "boot_notification_received_at": datetime.utcnow().isoformat(),
                    "charge_point_vendor": charge_point_vendor,
                    "charge_point_model": charge_point_model,
                    "firmware_version": firmware_version,
                    "last_boot_time": datetime.utcnow().isoformat()
                })
                
                # Update charger metadata
                charger.updated_at = datetime.utcnow()
                
                db.commit()
                
                logging.info(f"Updated charger {self.charge_point_id} with BootNotification data: vendor={charger.vendor}, model={charger.model}, firmware={charger.firmware_version}")
                logging.info(f"Configuration updated with {len(charger.configuration)} fields")
                
            except Exception as e:
                logging.error(f"Failed to update charger {self.charge_point_id} with BootNotification: {e}")
                db.rollback()
            finally:
                db.close()
                
        except Exception as e:
            logging.error(f"Error saving BootNotification to database: {e}")

    @on(Action.CancelReservation)
    async def on_cancel_reservation(self, reservation_id, **kwargs):
        try:
            logging.info(f"Received CancelReservation: reservation_id {reservation_id}")
            return call_result.CancelReservationPayload(
                status=ReservationStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_cancel_reservation: {e}")
            raise

    @on(Action.ChangeAvailability)
    async def on_change_availability(self, connector_id, type, **kwargs):
        try:
            logging.info(f"Received ChangeAvailability: connector_id {connector_id}, type {type}")
            return call_result.ChangeAvailabilityPayload(
                status=AvailabilityStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_change_availability: {e}")
            raise

    @on(Action.ChangeConfiguration)
    async def on_change_configuration(self, key, value, **kwargs):
        try:
            logging.info(f"Received ChangeConfiguration: key {key}, value {value}")
            return call_result.ChangeConfigurationPayload(
                status=ConfigurationStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_change_configuration: {e}")
            raise

    @on(Action.ClearCache)
    async def on_clear_cache(self, **kwargs):
        try:
            logging.info("Received ClearCache")
            return call_result.ClearCachePayload(
                status=ClearCacheStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_clear_cache: {e}")
            raise

    @on(Action.ClearChargingProfile)
    async def on_clear_charging_profile(self, id=None, connector_id=None, charging_profile_purpose=None, stack_level=None, **kwargs):
        try:
            logging.info(f"Received ClearChargingProfile: id {id}, connector_id {connector_id}, purpose {charging_profile_purpose}, stack_level {stack_level}")
            return call_result.ClearChargingProfilePayload(
                status=ChargingProfileStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_clear_charging_profile: {e}")
            raise

    @on(Action.DataTransfer)
    async def on_data_transfer(self, vendor_id, message_id=None, data=None, **kwargs):
        try:
            logging.info(f"Received DataTransfer: vendor_id {vendor_id}, message_id {message_id}, data {data}")
            
            # Handle malformed JSON in data field
            if isinstance(data, str):
                try:
                    # Try to parse the data as JSON to validate it
                    import json
                    json.loads(data)
                    logging.info(f"DataTransfer data is valid JSON: {data}")
                except json.JSONDecodeError as json_err:
                    logging.warning(f"DataTransfer contains invalid JSON in data field: {json_err}")
                    logging.warning(f"Raw data: {data}")
                    # Still accept the message but log the issue
                    
            return call_result.DataTransferPayload(
                status=DataTransferStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_data_transfer: {e}")
            raise

    @on(Action.DiagnosticsStatusNotification)
    async def on_diagnostics_status_notification(self, status, **kwargs):
        try:
            logging.info(f"Received DiagnosticsStatusNotification: status {status}")
            return call_result.DiagnosticsStatusNotificationPayload()
        except Exception as e:
            logging.error(f"Error in on_diagnostics_status_notification: {e}")
            raise

    @on(Action.FirmwareStatusNotification)
    async def on_firmware_status_notification(self, status, **kwargs):
        try:
            logging.info(f"Received FirmwareStatusNotification: status {status}")
            return call_result.FirmwareStatusNotificationPayload()
        except Exception as e:
            logging.error(f"Error in on_firmware_status_notification: {e}")
            raise

    @on(Action.GetCompositeSchedule)
    async def on_get_composite_schedule(self, connector_id, duration, charging_rate_unit=None, **kwargs):
        try:
            logging.info(f"Received GetCompositeSchedule: connector_id {connector_id}, duration {duration}, charging_rate_unit {charging_rate_unit}")
            return call_result.GetCompositeSchedulePayload(
                status=GetCompositeScheduleStatus.accepted,
                connector_id=connector_id,
                schedule_start=datetime.now().isoformat(),
                charging_schedule={
                    "chargingRateUnit": charging_rate_unit or "W",
                    "chargingSchedulePeriod": [
                        {
                            "startPeriod": 0,
                            "limit": 10000  # 10 kW
                        }
                    ]
                }
            )
        except Exception as e:
            logging.error(f"Error in on_get_composite_schedule: {e}")
            raise

    @on(Action.GetConfiguration)
    async def on_get_configuration(self, key=None, **kwargs):
        try:
            logging.info(f"Received GetConfiguration: key {key}")
            configuration_key = [{"key": "example_key", "value": "example_value"}] if not key else []
            return call_result.GetConfigurationPayload(
                configuration_key=configuration_key
            )
        except Exception as e:
            logging.error(f"Error in on_get_configuration: {e}")
            raise

    @on(Action.GetDiagnostics)
    async def on_get_diagnostics(self, location, start_time=None, stop_time=None, retries=None, retry_interval=None, **kwargs):
        try:
            logging.info(f"Received GetDiagnostics: location {location}, start_time {start_time}, stop_time {stop_time}")
            return call_result.GetDiagnosticsPayload(
                file_name="diagnostics.log"
            )
        except Exception as e:
            logging.error(f"Error in on_get_diagnostics: {e}")
            raise

    @on(Action.GetLocalListVersion)
    async def on_get_local_list_version(self, **kwargs):
        try:
            logging.info("Received GetLocalListVersion")
            return call_result.GetLocalListVersionPayload(
                list_version=1
            )
        except Exception as e:
            logging.error(f"Error in on_get_local_list_version: {e}")
            raise

    @on(Action.Heartbeat)
    async def on_heartbeat(self, **kwargs):
        try:
            logging.info("Received Heartbeat")
            return call_result.HeartbeatPayload(
                current_time=datetime.now().isoformat()
            )
        except Exception as e:
            logging.error(f"Error in on_heartbeat: {e}")
            raise

    @on(Action.MeterValues)
    async def on_meter_values(self, connector_id, transaction_id, meter_value, **kwargs):
        try:
            logging.info(f"Received MeterValues: connector_id {connector_id}, transaction_id {transaction_id}")
            
            # Forward to master
            await client_manager.broadcast_to_master({
                "message_type": "ocpp_forward",
                "charger_id": self.charge_point_id,
                "direction": "incoming",
                "ocpp_message": [2, "meter", "MeterValues", {
                    "connectorId": connector_id,
                    "transactionId": transaction_id,
                    "meterValue": meter_value,
                    **kwargs
                }]
            })
            
            return call_result.MeterValuesPayload()
        except Exception as e:
            logging.error(f"Error in on_meter_values: {e}")
            raise

    @on(Action.RemoteStartTransaction)
    async def on_remote_start_transaction(self, id_tag, connector_id=None, **kwargs):
        try:
            logging.info(f"Received RemoteStartTransaction: id_tag {id_tag}, connector_id {connector_id}")
            return call_result.RemoteStartTransactionPayload(
                status=RemoteStartStopStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_remote_start_transaction: {e}")
            raise

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop_transaction(self, transaction_id, **kwargs):
        try:
            logging.info(f"Received RemoteStopTransaction: transaction_id {transaction_id}")
            return call_result.RemoteStopTransactionPayload(
                status=RemoteStartStopStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_remote_stop_transaction: {e}")
            raise

    @on(Action.ReserveNow)
    async def on_reserve_now(self, connector_id, expiry_date, id_tag, reservation_id, parent_id_tag=None, **kwargs):
        try:
            logging.info(f"Received ReserveNow: connector_id {connector_id}, reservation_id {reservation_id}, id_tag {id_tag}")
            return call_result.ReserveNowPayload(
                status=ReservationStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_reserve_now: {e}")
            raise

    @on(Action.Reset)
    async def on_reset(self, type, **kwargs):
        try:
            logging.info(f"Received Reset: type {type}")
            return call_result.ResetPayload(
                status=ResetStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_reset: {e}")
            raise

    @on(Action.SendLocalList)
    async def on_send_local_list(self, list_version, update_type, local_authorization_list=None, **kwargs):
        try:
            logging.info(f"Received SendLocalList: list_version {list_version}, update_type {update_type}")
            return call_result.SendLocalListPayload(
                status=DataTransferStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_send_local_list: {e}")
            raise

    @on(Action.SetChargingProfile)
    async def on_set_charging_profile(self, connector_id, cs_charging_profiles, **kwargs):
        try:
            logging.info(f"Received SetChargingProfile: connector_id {connector_id}, profiles {cs_charging_profiles}")
            return call_result.SetChargingProfilePayload(
                status=ChargingProfileStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_set_charging_profile: {e}")
            raise

    @on(Action.StartTransaction)
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        try:
            self.transaction_counter += 1  # Increment transaction counter
            logging.info(f"Received StartTransaction: connector_id {connector_id}, id_tag {id_tag}, transaction_id {self.transaction_counter}")
            
            # Forward incoming request to master
            await client_manager.broadcast_to_master({
                "message_type": "ocpp_forward",
                "charger_id": self.charge_point_id,
                "direction": "incoming",
                "ocpp_message": [2, "start", "StartTransaction", {
                    "connectorId": connector_id,
                    "idTag": id_tag,
                    "meterStart": meter_start,
                    "timestamp": timestamp,
                    **kwargs
                }]
            })
            
            # Forward outgoing response to master (so Laravel gets the transaction_id)
            await client_manager.broadcast_to_master({
                "message_type": "ocpp_forward",
                "charger_id": self.charge_point_id,
                "direction": "outgoing",
                "ocpp_message": [3, "start", {
                    "transactionId": self.transaction_counter,
                    "idTagInfo": {'status': AuthorizationStatus.accepted}
                }]
            })
            
            return call_result.StartTransactionPayload(
                transaction_id=self.transaction_counter,
                id_tag_info={'status': AuthorizationStatus.accepted}
            )
        except Exception as e:
            logging.error(f"Error in on_start_transaction: {e}")
            raise

    @on(Action.StatusNotification)
    async def on_status_notification(self, connector_id, error_code, status, **kwargs):
        try:
            logging.info(f"Received StatusNotification: connector_id {connector_id}, status {status}, error_code {error_code}")
            
            # Forward to master
            await client_manager.broadcast_to_master({
                "message_type": "ocpp_forward",
                "charger_id": self.charge_point_id,
                "direction": "incoming",
                "ocpp_message": [2, "status", "StatusNotification", {
                    "connectorId": connector_id,
                    "errorCode": error_code,
                    "status": status,
                    **kwargs
                }]
            })
            
            return call_result.StatusNotificationPayload()
        except Exception as e:
            logging.error(f"Error in on_status_notification: {e}")
            raise

    @on(Action.StopTransaction)
    async def on_stop_transaction(self, transaction_id, id_tag, meter_stop, timestamp, **kwargs):
        try:
            logging.info(f"Received StopTransaction: transaction_id {transaction_id}, id_tag {id_tag}")
            
            # Forward incoming request to master
            await client_manager.broadcast_to_master({
                "message_type": "ocpp_forward",
                "charger_id": self.charge_point_id,
                "direction": "incoming",
                "ocpp_message": [2, "stop", "StopTransaction", {
                    "transactionId": transaction_id,
                    "idTag": id_tag,
                    "meterStop": meter_stop,
                    "timestamp": timestamp,
                    **kwargs
                }]
            })
            
            # Forward outgoing response to master
            await client_manager.broadcast_to_master({
                "message_type": "ocpp_forward",
                "charger_id": self.charge_point_id,
                "direction": "outgoing",
                "ocpp_message": [3, "stop", {
                    "idTagInfo": {'status': AuthorizationStatus.accepted}
                }]
            })
            
            return call_result.StopTransactionPayload(
                id_tag_info={'status': AuthorizationStatus.accepted}
            )
        except Exception as e:
            logging.error(f"Error in on_stop_transaction: {e}")
            raise

    @on(Action.TriggerMessage)
    async def on_trigger_message(self, requested_message, connector_id=None, **kwargs):
        try:
            logging.info(f"Received TriggerMessage: requested_message {requested_message}, connector_id {connector_id}")
            return call_result.TriggerMessagePayload(
                status=TriggerMessageStatus.accepted
            )
        except Exception as e:
            logging.error(f"Error in on_trigger_message: {e}")
            raise

    @on(Action.UnlockConnector)
    async def on_unlock_connector(self, connector_id, **kwargs):
        try:
            logging.info(f"Received UnlockConnector: connector_id {connector_id}")
            return call_result.UnlockConnectorPayload(
                status='Unlocked'
            )
        except Exception as e:
            logging.error(f"Error in on_unlock_connector: {e}")
            raise

    @on(Action.UpdateFirmware)
    async def on_update_firmware(self, location, retrieve_date, retries=None, retry_interval=None, **kwargs):
        try:
            logging.info(f"Received UpdateFirmware: location {location}, retrieve_date {retrieve_date}")
            return call_result.UpdateFirmwarePayload()
        except Exception as e:
            logging.error(f"Error in on_update_firmware: {e}")
            raise


async def handle_client_connection(websocket, path):
    """Handle regular client connections with custom message parsing"""
    charge_point_id = path.split('/')[-1]
    logging.info(f"Client connecting: {charge_point_id}")
    
    # Create a custom websocket wrapper to handle malformed messages
    class CustomWebSocket:
        def __init__(self, websocket):
            self.websocket = websocket
            
        async def recv(self):
            """Custom recv that handles malformed JSON"""
            try:
                message = await self.websocket.recv()
                
                # Try to parse the message to check for JSON issues
                import json
                try:
                    parsed = json.loads(message)
                    
                    # Check if it's a DataTransfer message with malformed data field
                    if (isinstance(parsed, list) and len(parsed) >= 4 and 
                        parsed[2] == "DataTransfer" and isinstance(parsed[3], dict)):
                        
                        data_field = parsed[3].get("data")
                        if isinstance(data_field, str):
                            try:
                                # Try to parse the data field as JSON
                                json.loads(data_field)
                            except json.JSONDecodeError:
                                logging.warning(f"Detected malformed JSON in DataTransfer data field")
                                logging.warning(f"Original message: {message}")
                                
                                # Fix the malformed JSON by escaping quotes in the data field
                                try:
                                    # Extract the data field and fix it
                                    data_value = parsed[3]["data"]
                                    # Escape quotes in the data field
                                    fixed_data = data_value.replace('"', '\\"')
                                    parsed[3]["data"] = fixed_data
                                    
                                    # Reconstruct the message
                                    fixed_message = json.dumps(parsed)
                                    logging.info(f"Fixed malformed JSON message")
                                    return fixed_message
                                except Exception as fix_err:
                                    logging.error(f"Failed to fix malformed JSON: {fix_err}")
                                    # Return original message and let OCPP handle the error
                                    
                except json.JSONDecodeError:
                    # Not a JSON message, return as-is
                    pass
                    
                return message
                
            except Exception as e:
                logging.error(f"Error in custom recv: {e}")
                raise
                
        def __getattr__(self, name):
            """Delegate all other attributes to the original websocket"""
            return getattr(self.websocket, name)
    
    # Use the custom websocket wrapper
    custom_websocket = CustomWebSocket(websocket)
    central_system = CentralSystem(charge_point_id, custom_websocket)
    
    # Create charger record with default values if it doesn't exist
    await create_charger_on_connect(charge_point_id, websocket)
    
    try:
        await central_system.start()
    except websockets.exceptions.ConnectionClosedOK:
        # Normal client disconnect - not an error
        logging.info(f"Client {charge_point_id} disconnected normally")
    except websockets.exceptions.ConnectionClosed:
        # Client disconnected unexpectedly
        logging.warning(f"Client {charge_point_id} disconnected unexpectedly")
    except Exception as e:
        logging.error(f"Error handling client {charge_point_id}: {e}")

async def create_charger_on_connect(charge_point_id, websocket):
    """Create charger record with default values when WebSocket connects"""
    try:
        from app.models.database import SessionLocal, Charger
        from datetime import datetime
        
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charge_point_id).first()
            
            if not charger:
                # Extract connection information from websocket
                remote_address = None
                user_agent = None
                subprotocol = None
                
                try:
                    remote_address = websocket.remote_address[0] if websocket.remote_address else None
                    user_agent = websocket.request_headers.get('User-Agent')
                    subprotocol = websocket.subprotocol
                    logging.info(f"Extracted websocket info: remote={remote_address}, user_agent={user_agent}, subprotocol={subprotocol}")
                except Exception as e:
                    logging.warning(f"Could not extract websocket info: {e}")
                
                # Create new charger with default values
                charger = Charger(
                    id=charge_point_id,
                    vendor="Unknown",
                    model="Unknown",
                    serial_number="Unknown",
                    firmware_version="Unknown",
                    status="Connecting",
                    is_connected=True,
                    connection_time=datetime.utcnow(),
                    last_heartbeat=datetime.utcnow(),
                    configuration={
                        "remote_address": remote_address,
                        "user_agent": user_agent,
                        "subprotocol": subprotocol,
                        "connection_source": "websocket"
                    }
                )
                db.add(charger)
                logging.info(f"Created new charger record for {charge_point_id} with default values")
            else:
                # Update existing charger connection info
                charger.is_connected = True
                charger.connection_time = datetime.utcnow()
                charger.status = "Connecting"
                charger.updated_at = datetime.utcnow()
                
                # Update configuration with connection info
                if not charger.configuration:
                    charger.configuration = {}
                
                try:
                    charger.configuration.update({
                        "remote_address": websocket.remote_address[0] if websocket.remote_address else None,
                        "user_agent": websocket.request_headers.get('User-Agent'),
                        "subprotocol": websocket.subprotocol,
                        "last_connection_time": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logging.warning(f"Could not update charger configuration: {e}")
                
                logging.info(f"Updated existing charger record for {charge_point_id}")
            
            db.commit()
            logging.info(f"Successfully committed charger {charge_point_id} to database")
            
        except Exception as e:
            logging.error(f"Failed to create/update charger {charge_point_id}: {e}")
            db.rollback()
        finally:
            db.close()
            
    except Exception as e:
        logging.error(f"Error creating charger on connect: {e}")

async def main():
    try:
        # Create an SSL context for WSS
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")  # Update paths if needed
        
        # Configure cipher suites to support TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA
        ssl_context.set_ciphers('ECDHE-RSA-AES128-SHA:ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        # Set minimum TLS version to ensure compatibility
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        # Log the configured cipher suites
        logging.info(f"SSL Context configured with cipher suites: {ssl_context.get_ciphers()}")
        logging.info(f"Minimum TLS version: {ssl_context.minimum_version}")

        # Start server with both client and master connection handlers
        async with websockets.serve(
            lambda ws, path: (
                client_manager.handle_master_connection(ws, path) 
                if path.startswith('/master') 
                else handle_client_connection(ws, path)
            ),
            "0.0.0.0",
            9000,
            subprotocols=["ocpp1.6"],
            ssl=ssl_context  # Add SSL context for WSS
        ):
            logging.info("OCPP 1.6 server running on wss://0.0.0.0:9000")
            logging.info("Regular clients connect to: wss://0.0.0.0:9000/{charge_point_id}")
            logging.info("Master connections connect to: wss://0.0.0.0:9000/master")
            await asyncio.Future()  # Run forever
    except Exception as e:
        logging.error(f"Server failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
