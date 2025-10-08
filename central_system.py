import asyncio
import logging
from datetime import datetime
import ssl
import websockets
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

class CentralSystem(cp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logging.debug("CentralSystem initialized with route_map: %s", self.route_map)

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
            logging.info(f"Received StartTransaction: connector_id {connector_id}, id_tag {id_tag}")
            return call_result.StartTransaction(
                transaction_id=1,
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

async def main():
    try:
        # Create an SSL context for WSS
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")  # Update paths if needed

        async with websockets.serve(
            lambda ws, path: CentralSystem(path.split('/')[-1], ws).start(),
            "localhost",
            9000,
            subprotocols=["ocpp1.6"],
            ssl=ssl_context  # Add SSL context for WSS
        ):
            logging.info("OCPP 1.6 server running on wss://localhost:9000")
            await asyncio.Future()  # Run forever
    except Exception as e:
        logging.error(f"Server failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())