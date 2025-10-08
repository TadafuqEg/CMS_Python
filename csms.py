import asyncio
import logging
from datetime import datetime

import websockets
import ocpp.exceptions
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16.call import BootNotification, Heartbeat, StatusNotification, StartTransaction, MeterValues, StopTransaction
from ocpp.v16.call_result import Authorize, Reset, ChangeAvailability, ChangeConfiguration, ClearCache, GetConfiguration, GetLocalListVersion, RemoteStartTransaction, RemoteStopTransaction, SendLocalList, UnlockConnector
from ocpp.v16.enums import (
    Action,
    AuthorizationStatus,
    AvailabilityStatus,
    AvailabilityType,
    ChargePointErrorCode,
    ChargePointStatus,
    ConfigurationStatus,
    RegistrationStatus,
    ResetStatus,
    ResetType,
    UnlockStatus
)

logging.basicConfig(level=logging.INFO)

class MyChargePoint(cp):
    def __init__(self, charge_point_id, websocket):
        super().__init__(charge_point_id, websocket)
        self.transaction_id = None
        self.connector_id = 1
        self.status = ChargePointStatus.available

    async def send_boot_notification(self):
        request = BootNotification(
            charge_point_model="Model XYZ",
            charge_point_vendor="Vendor ABC",
            firmware_version="1.0.0"
        )
        try:
            response = await self.call(request)
            if response and hasattr(response, 'status'):
                if response.status == RegistrationStatus.accepted:
                    logging.info("BootNotification accepted. Heartbeat interval: %s", response.interval)
                    return response.interval
                else:
                    logging.error("BootNotification failed: %s", response.status)
                    return None
            else:
                logging.error("BootNotification response is None or invalid")
                return None
        except ocpp.exceptions.ProtocolError as e:
            logging.error(f"BootNotification failed with ProtocolError: {e}")
            return None
        except ocpp.exceptions.NotImplementedError as e:
            logging.error(f"BootNotification failed with NotImplementedError: {e}")
            return None
        except Exception as e:
            logging.error(f"BootNotification failed with unexpected error: {e}")
            return None

    async def send_heartbeat(self, interval):
        while True:
            request = Heartbeat()
            try:
                await self.call(request)
            except ocpp.exceptions.ProtocolError as e:
                logging.error(f"Heartbeat failed with ProtocolError: {e}")
            except ocpp.exceptions.NotImplementedError as e:
                logging.error(f"Heartbeat failed with NotImplementedError: {e}")
            except Exception as e:
                logging.error(f"Heartbeat failed with unexpected error: {e}")
            await asyncio.sleep(interval)

    async def send_status_notification(self):
        request = StatusNotification(
            connector_id=self.connector_id,
            error_code=ChargePointErrorCode.no_error,
            status=self.status
        )
        try:
            await self.call(request)
        except ocpp.exceptions.ProtocolError as e:
            logging.error(f"StatusNotification failed with ProtocolError: {e}")
        except ocpp.exceptions.NotImplementedError as e:
            logging.error(f"StatusNotification failed with NotImplementedError: {e}")
        except Exception as e:
            logging.error(f"StatusNotification failed with unexpected error: {e}")

    async def start_transaction(self, id_tag):
        if self.status != ChargePointStatus.available:
            logging.warning("Cannot start transaction: Connector not available")
            return None
        request = StartTransaction(
            connector_id=self.connector_id,
            id_tag=id_tag,
            meter_start=0,
            timestamp=datetime.utcnow().isoformat()
        )
        try:
            response = await self.call(request)
            if response and hasattr(response, 'id_tag_info'):
                if response.id_tag_info['status'] == AuthorizationStatus.accepted:
                    self.transaction_id = response.transaction_id
                    self.status = ChargePointStatus.charging
                    await self.send_status_notification()
                    logging.info("Transaction started: ID %s", self.transaction_id)
                    return self.transaction_id
                else:
                    logging.error("StartTransaction failed")
                    return None
            else:
                logging.error("StartTransaction response is None or invalid")
                return None
        except ocpp.exceptions.ProtocolError as e:
            logging.error(f"StartTransaction failed with ProtocolError: {e}")
            return None
        except ocpp.exceptions.NotImplementedError as e:
            logging.error(f"StartTransaction failed with NotImplementedError: {e}")
            return None
        except Exception as e:
            logging.error(f"StartTransaction failed with unexpected error: {e}")
            return None

    async def send_meter_values(self, transaction_id):
        request = MeterValues(
            connector_id=self.connector_id,
            transaction_id=transaction_id,
            meter_value=[{
                'timestamp': datetime.utcnow().isoformat(),
                'sampled_value': [{'value': '100', 'measurand': 'Energy.Active.Import.Register'}]
            }]
        )
        try:
            await self.call(request)
        except ocpp.exceptions.ProtocolError as e:
            logging.error(f"MeterValues failed with ProtocolError: {e}")
        except ocpp.exceptions.NotImplementedError as e:
            logging.error(f"MeterValues failed with NotImplementedError: {e}")
        except Exception as e:
            logging.error(f"MeterValues failed with unexpected error: {e}")

    async def stop_transaction(self, transaction_id, id_tag):
        request = StopTransaction(
            transaction_id=transaction_id,
            id_tag=id_tag,
            meter_stop=100,
            timestamp=datetime.utcnow().isoformat()
        )
        try:
            response = await self.call(request)
            if response and hasattr(response, 'id_tag_info'):
                if response.id_tag_info['status'] == AuthorizationStatus.accepted:
                    self.transaction_id = None
                    self.status = ChargePointStatus.available
                    await self.send_status_notification()
                    logging.info("Transaction stopped")
                else:
                    logging.error("StopTransaction failed")
            else:
                logging.error("StopTransaction response is None or invalid")
        except ocpp.exceptions.ProtocolError as e:
            logging.error(f"StopTransaction failed with ProtocolError: {e}")
        except ocpp.exceptions.NotImplementedError as e:
            logging.error(f"StopTransaction failed with NotImplementedError: {e}")
        except Exception as e:
            logging.error(f"StopTransaction failed with unexpected error: {e}")

    async def send_boot_notification_and_heartbeat(self):
        interval = await self.send_boot_notification()
        if interval:
            await self.send_status_notification()
            await self.send_heartbeat(interval)

    @on(Action.authorize)
    async def on_authorize(self, id_tag, **kwargs):
        return Authorize(
            id_tag_info={'status': AuthorizationStatus.accepted}
        )

    @on(Action.reset)
    async def on_reset(self, type, **kwargs):
        logging.info("Received Reset request of type: %s", type)
        if type == ResetType.soft:
            self.status = ChargePointStatus.available
            await self.send_status_notification()
        return Reset(status=ResetStatus.accepted)

    @on(Action.change_availability)
    async def on_change_availability(self, connector_id, type, **kwargs):
        logging.info("ChangeAvailability for connector %s to %s", connector_id, type)
        if type == AvailabilityType.operative:
            self.status = ChargePointStatus.available
        else:
            self.status = ChargePointStatus.unavailable
        await self.send_status_notification()
        return ChangeAvailability(status=AvailabilityStatus.accepted)

    @on(Action.change_configuration)
    async def on_change_configuration(self, key, value, **kwargs):
        logging.info("ChangeConfiguration: %s = %s", key, value)
        return ChangeConfiguration(status=ConfigurationStatus.accepted)

    @on(Action.clear_cache)
    async def on_clear_cache(self, **kwargs):
        logging.info("ClearCache requested")
        return ClearCache(status='Accepted')

    @on(Action.get_configuration)
    async def on_get_configuration(self, key=None, **kwargs):
        logging.info("GetConfiguration for keys: %s", key)
        return GetConfiguration(
            configuration_key=[{'key': 'HeartbeatInterval', 'value': '60', 'readonly': False}]
        )

    @on(Action.get_local_list_version)
    async def on_get_local_list_version(self, **kwargs):
        return GetLocalListVersion(list_version=1)

    @on(Action.remote_start_transaction)
    async def on_remote_start_transaction(self, id_tag, connector_id=None, **kwargs):
        logging.info("RemoteStartTransaction for id_tag: %s", id_tag)
        transaction_id = await self.start_transaction(id_tag)
        return RemoteStartTransaction(status='Accepted' if transaction_id else 'Rejected')

    @on(Action.remote_stop_transaction)
    async def on_remote_stop_transaction(self, transaction_id, **kwargs):
        logging.info("RemoteStopTransaction for ID: %s", transaction_id)
        if self.transaction_id == transaction_id:
            await self.stop_transaction(transaction_id, 'remote_stop')
            return RemoteStopTransaction(status='Accepted')
        return RemoteStopTransaction(status='Rejected')

    @on(Action.send_local_list)
    async def on_send_local_list(self, list_version, update_type, local_authorization_list=None, **kwargs):
        logging.info("SendLocalList version %s, type %s", list_version, update_type)
        return SendLocalList(status='Accepted')

    @on(Action.unlock_connector)
    async def on_unlock_connector(self, connector_id, **kwargs):
        logging.info("UnlockConnector for %s", connector_id)
        return UnlockConnector(status=UnlockStatus.unlocked)

async def main():
    charge_point_id = 'CP_1'
    central_system_url = 'ws://localhost:9000/' + charge_point_id

    try:
        async with websockets.connect(
            central_system_url,
            subprotocols=['ocpp1.6']
        ) as ws:
            charge_point = MyChargePoint(charge_point_id, ws)
            await asyncio.gather(
                charge_point.start(),
                charge_point.send_boot_notification_and_heartbeat()
            )
    except Exception as e:
        logging.error(f"Connection failed: {e}")

if __name__ == '__main__':
    asyncio.run(main())
