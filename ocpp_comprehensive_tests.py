#!/usr/bin/env python3
"""
Comprehensive OCPP 1.6 Test Suite
Tests all OCPP messages from the Postman Testing Guide
"""

import asyncio
import ssl
import websockets
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

class OCPPTester:
    def __init__(self, server_url: str = "wss://localhost:9000", charge_point_id: str = "CP001"):
        self.server_url = server_url
        self.charge_point_id = charge_point_id
        self.websocket = None
        self.test_rfid = "RFID123456789"
        self.test_connector_id = 1
        self.test_transaction_id = 12345
        self.reservation_id = 54321
        
        # Create SSL context for testing (disable certificate verification)
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # Test results
        self.test_results = []
        
    async def connect(self):
        """Connect to OCPP server"""
        try:
            self.websocket = await websockets.connect(
                f"{self.server_url}/{self.charge_point_id}",
                ssl=self.ssl_context,
                subprotocols=["ocpp1.6"]
            )
            print(f"✅ Connected to OCPP server: {self.server_url}/{self.charge_point_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from OCPP server"""
        if self.websocket:
            await self.websocket.close()
            print("🔌 Disconnected from OCPP server")
    
    async def send_message(self, message: List[Any], expected_response_type: str = None) -> Dict[str, Any]:
        """Send OCPP message and wait for response"""
        try:
            message_json = json.dumps(message)
            print(f"📤 Sending: {message_json}")
            
            await self.websocket.send(message_json)
            
            # Wait for response
            response_json = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            response = json.loads(response_json)
            
            print(f"📥 Received: {response_json}")
            
            # Validate response
            if expected_response_type:
                if len(response) >= 3 and response[2] == expected_response_type:
                    print(f"✅ Response type matches expected: {expected_response_type}")
                else:
                    print(f"❌ Response type mismatch. Expected: {expected_response_type}, Got: {response[2] if len(response) >= 3 else 'Unknown'}")
            
            return {
                "success": True,
                "request": message,
                "response": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except asyncio.TimeoutError:
            print("⏰ Timeout waiting for response")
            return {
                "success": False,
                "request": message,
                "error": "Timeout",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"❌ Error: {e}")
            return {
                "success": False,
                "request": message,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def log_test_result(self, test_name: str, result: Dict[str, Any]):
        """Log test result"""
        self.test_results.append({
            "test_name": test_name,
            "result": result
        })
        
        if result["success"]:
            print(f"✅ {test_name}: PASSED")
        else:
            print(f"❌ {test_name}: FAILED - {result.get('error', 'Unknown error')}")
    
    # Core Profile Messages
    async def test_boot_notification(self):
        """Test BootNotification message"""
        print("\n🔧 Testing BootNotification")
        print("=" * 50)
        
        message = [2, "boot_001", "BootNotification", {
            "chargePointVendor": "Commercial MINI DC",
            "chargePointModel": "CMDC-60kW",
            "chargePointSerialNumber": "CMDC001234567",
            "chargeBoxSerialNumber": "BOX001234567",
            "firmwareVersion": "1.0.0"
        }]
        
        result = await self.send_message(message, "BootNotification")
        self.log_test_result("BootNotification", result)
        return result
    
    async def test_authorize(self):
        """Test Authorize message"""
        print("\n🔧 Testing Authorize")
        print("=" * 50)
        
        message = [2, "auth_001", "Authorize", {
            "idTag": self.test_rfid
        }]
        
        result = await self.send_message(message, "Authorize")
        self.log_test_result("Authorize", result)
        return result
    
    async def test_start_transaction(self):
        """Test StartTransaction message"""
        print("\n🔧 Testing StartTransaction")
        print("=" * 50)
        
        message = [2, "start_001", "StartTransaction", {
            "connectorId": self.test_connector_id,
            "idTag": self.test_rfid,
            "meterStart": 1000,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
        
        result = await self.send_message(message, "StartTransaction")
        self.log_test_result("StartTransaction", result)
        return result
    
    async def test_stop_transaction(self):
        """Test StopTransaction message"""
        print("\n🔧 Testing StopTransaction")
        print("=" * 50)
        
        message = [2, "stop_001", "StopTransaction", {
            "transactionId": self.test_transaction_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "meterStop": 1500,
            "reason": "Local"
        }]
        
        result = await self.send_message(message, "StopTransaction")
        self.log_test_result("StopTransaction", result)
        return result
    
    async def test_heartbeat(self):
        """Test Heartbeat message"""
        print("\n🔧 Testing Heartbeat")
        print("=" * 50)
        
        message = [2, "heart_001", "Heartbeat", {}]
        
        result = await self.send_message(message, "Heartbeat")
        self.log_test_result("Heartbeat", result)
        return result
    
    async def test_status_notification(self):
        """Test StatusNotification message"""
        print("\n🔧 Testing StatusNotification")
        print("=" * 50)
        
        message = [2, "status_001", "StatusNotification", {
            "connectorId": self.test_connector_id,
            "errorCode": "NoError",
            "status": "Available",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
        
        result = await self.send_message(message, "StatusNotification")
        self.log_test_result("StatusNotification", result)
        return result
    
    async def test_meter_values(self):
        """Test MeterValues message"""
        print("\n🔧 Testing MeterValues")
        print("=" * 50)
        
        message = [2, "meter_001", "MeterValues", {
            "connectorId": self.test_connector_id,
            "transactionId": self.test_transaction_id,
            "meterValue": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [
                        {
                            "value": "1500",
                            "context": "Sample.Periodic",
                            "format": "Raw",
                            "measurand": "Energy.Active.Import.Register",
                            "unit": "Wh"
                        },
                        {
                            "value": "7.5",
                            "context": "Sample.Periodic",
                            "format": "Raw",
                            "measurand": "Power.Active.Import",
                            "unit": "kW"
                        },
                        {
                            "value": "230",
                            "context": "Sample.Periodic",
                            "format": "Raw",
                            "measurand": "Voltage",
                            "unit": "V"
                        },
                        {
                            "value": "32.6",
                            "context": "Sample.Periodic",
                            "format": "Raw",
                            "measurand": "Current.Import",
                            "unit": "A"
                        }
                    ]
                }
            ]
        }]
        
        result = await self.send_message(message, "MeterValues")
        self.log_test_result("MeterValues", result)
        return result
    
    # Firmware Management Messages
    async def test_get_diagnostics(self):
        """Test GetDiagnostics message"""
        print("\n🔧 Testing GetDiagnostics")
        print("=" * 50)
        
        message = [2, "diag_001", "GetDiagnostics", {
            "location": "http://192.168.60.37:8000/api/v1/diagnostics",
            "retries": 3,
            "retryInterval": 60
        }]
        
        result = await self.send_message(message, "GetDiagnostics")
        self.log_test_result("GetDiagnostics", result)
        return result
    
    async def test_update_firmware(self):
        """Test UpdateFirmware message"""
        print("\n🔧 Testing UpdateFirmware")
        print("=" * 50)
        
        message = [2, "fw_001", "UpdateFirmware", {
            "location": "http://192.168.60.37:8000/api/v1/firmware/update.bin",
            "retries": 3,
            "retryInterval": 60,
            "retrieveDate": datetime.now(timezone.utc).isoformat()
        }]
        
        result = await self.send_message(message, "UpdateFirmware")
        self.log_test_result("UpdateFirmware", result)
        return result
    
    # Local Authorization List Management
    async def test_get_local_list_version(self):
        """Test GetLocalListVersion message"""
        print("\n🔧 Testing GetLocalListVersion")
        print("=" * 50)
        
        message = [2, "list_001", "GetLocalListVersion", {}]
        
        result = await self.send_message(message, "GetLocalListVersion")
        self.log_test_result("GetLocalListVersion", result)
        return result
    
    async def test_send_local_list(self):
        """Test SendLocalList message"""
        print("\n🔧 Testing SendLocalList")
        print("=" * 50)
        
        message = [2, "send_001", "SendLocalList", {
            "listVersion": 1,
            "updateType": "Full",
            "localAuthorizationList": [
                {
                    "idTag": self.test_rfid,
                    "idTagInfo": {
                        "status": "Accepted",
                        "expiryDate": "2026-09-25T22:00:00+02:00"
                    }
                },
                {
                    "idTag": "RFID987654321",
                    "idTagInfo": {
                        "status": "Accepted",
                        "expiryDate": "2026-09-25T22:00:00+02:00"
                    }
                }
            ]
        }]
        
        result = await self.send_message(message, "SendLocalList")
        self.log_test_result("SendLocalList", result)
        return result
    
    # Reservation Profile
    async def test_reserve_now(self):
        """Test ReserveNow message"""
        print("\n🔧 Testing ReserveNow")
        print("=" * 50)
        
        message = [2, "reserve_001", "ReserveNow", {
            "connectorId": self.test_connector_id,
            "expiryDate": datetime.now(timezone.utc).isoformat(),
            "idTag": self.test_rfid,
            "reservationId": self.reservation_id
        }]
        
        result = await self.send_message(message, "ReserveNow")
        self.log_test_result("ReserveNow", result)
        return result
    
    async def test_cancel_reservation(self):
        """Test CancelReservation message"""
        print("\n🔧 Testing CancelReservation")
        print("=" * 50)
        
        message = [2, "cancel_001", "CancelReservation", {
            "reservationId": self.reservation_id
        }]
        
        result = await self.send_message(message, "CancelReservation")
        self.log_test_result("CancelReservation", result)
        return result
    
    # Remote Trigger Profile
    async def test_change_availability(self):
        """Test ChangeAvailability message"""
        print("\n🔧 Testing ChangeAvailability")
        print("=" * 50)
        
        message = [2, "avail_001", "ChangeAvailability", {
            "connectorId": self.test_connector_id,
            "type": "Operative"
        }]
        
        result = await self.send_message(message, "ChangeAvailability")
        self.log_test_result("ChangeAvailability", result)
        return result
    
    async def test_change_configuration(self):
        """Test ChangeConfiguration message"""
        print("\n🔧 Testing ChangeConfiguration")
        print("=" * 50)
        
        message = [2, "config_001", "ChangeConfiguration", {
            "key": "HeartbeatInterval",
            "value": "300"
        }]
        
        result = await self.send_message(message, "ChangeConfiguration")
        self.log_test_result("ChangeConfiguration", result)
        return result
    
    async def test_get_configuration(self):
        """Test GetConfiguration message"""
        print("\n🔧 Testing GetConfiguration")
        print("=" * 50)
        
        message = [2, "getconfig_001", "GetConfiguration", {
            "key": ["HeartbeatInterval", "MeterValueSampleInterval"]
        }]
        
        result = await self.send_message(message, "GetConfiguration")
        self.log_test_result("GetConfiguration", result)
        return result
    
    async def test_remote_start_transaction(self):
        """Test RemoteStartTransaction message"""
        print("\n🔧 Testing RemoteStartTransaction")
        print("=" * 50)
        
        message = [2, "remote_start_001", "RemoteStartTransaction", {
            "connectorId": self.test_connector_id,
            "idTag": self.test_rfid
        }]
        
        result = await self.send_message(message, "RemoteStartTransaction")
        self.log_test_result("RemoteStartTransaction", result)
        return result
    
    async def test_remote_stop_transaction(self):
        """Test RemoteStopTransaction message"""
        print("\n🔧 Testing RemoteStopTransaction")
        print("=" * 50)
        
        message = [2, "remote_stop_001", "RemoteStopTransaction", {
            "transactionId": self.test_transaction_id
        }]
        
        result = await self.send_message(message, "RemoteStopTransaction")
        self.log_test_result("RemoteStopTransaction", result)
        return result
    
    async def test_reset(self):
        """Test Reset message"""
        print("\n🔧 Testing Reset")
        print("=" * 50)
        
        message = [2, "reset_001", "Reset", {
            "type": "Hard"
        }]
        
        result = await self.send_message(message, "Reset")
        self.log_test_result("Reset", result)
        return result
    
    async def test_unlock_connector(self):
        """Test UnlockConnector message"""
        print("\n🔧 Testing UnlockConnector")
        print("=" * 50)
        
        message = [2, "unlock_001", "UnlockConnector", {
            "connectorId": self.test_connector_id
        }]
        
        result = await self.send_message(message, "UnlockConnector")
        self.log_test_result("UnlockConnector", result)
        return result
    
    # Data Transfer Profile
    async def test_data_transfer(self):
        """Test DataTransfer message"""
        print("\n🔧 Testing DataTransfer")
        print("=" * 50)
        
        message = [2, "data_001", "DataTransfer", {
            "vendorId": "Commercial MINI DC",
            "messageId": "CustomMessage",
            "data": "Custom data payload"
        }]
        
        result = await self.send_message(message, "DataTransfer")
        self.log_test_result("DataTransfer", result)
        return result
    
    # Test Scenarios
    async def test_complete_charging_session(self):
        """Test complete charging session scenario"""
        print("\n🔧 Testing Complete Charging Session Scenario")
        print("=" * 60)
        
        # 1. BootNotification
        await self.test_boot_notification()
        await asyncio.sleep(1)
        
        # 2. StatusNotification - Connector available
        await self.test_status_notification()
        await asyncio.sleep(1)
        
        # 3. Authorize
        await self.test_authorize()
        await asyncio.sleep(1)
        
        # 4. StartTransaction
        await self.test_start_transaction()
        await asyncio.sleep(1)
        
        # 5. MeterValues - Periodic energy reports
        await self.test_meter_values()
        await asyncio.sleep(1)
        
        # 6. StatusNotification - Connector charging
        status_msg = [2, "status_002", "StatusNotification", {
            "connectorId": self.test_connector_id,
            "errorCode": "NoError",
            "status": "Charging",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
        await self.send_message(status_msg, "StatusNotification")
        await asyncio.sleep(1)
        
        # 7. StopTransaction
        await self.test_stop_transaction()
        await asyncio.sleep(1)
        
        # 8. StatusNotification - Connector available again
        status_msg = [2, "status_003", "StatusNotification", {
            "connectorId": self.test_connector_id,
            "errorCode": "NoError",
            "status": "Available",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
        await self.send_message(status_msg, "StatusNotification")
        
        print("✅ Complete charging session scenario completed")
    
    async def test_remote_control_session(self):
        """Test remote control session scenario"""
        print("\n🔧 Testing Remote Control Session Scenario")
        print("=" * 60)
        
        # 1. BootNotification
        await self.test_boot_notification()
        await asyncio.sleep(1)
        
        # 2. GetConfiguration
        await self.test_get_configuration()
        await asyncio.sleep(1)
        
        # 3. ChangeConfiguration
        await self.test_change_configuration()
        await asyncio.sleep(1)
        
        # 4. RemoteStartTransaction
        await self.test_remote_start_transaction()
        await asyncio.sleep(1)
        
        # 5. MeterValues - Monitor charging progress
        await self.test_meter_values()
        await asyncio.sleep(1)
        
        # 6. RemoteStopTransaction
        await self.test_remote_stop_transaction()
        
        print("✅ Remote control session scenario completed")
    
    async def run_all_tests(self):
        """Run all OCPP message tests"""
        print("🚀 Starting Comprehensive OCPP 1.6 Test Suite")
        print("=" * 70)
        
        if not await self.connect():
            return
        
        try:
            # Core Profile Messages
            print("\n📋 CORE PROFILE MESSAGES")
            print("=" * 30)
            await self.test_boot_notification()
            await asyncio.sleep(1)
            await self.test_authorize()
            await asyncio.sleep(1)
            await self.test_start_transaction()
            await asyncio.sleep(1)
            await self.test_stop_transaction()
            await asyncio.sleep(1)
            await self.test_heartbeat()
            await asyncio.sleep(1)
            await self.test_status_notification()
            await asyncio.sleep(1)
            await self.test_meter_values()
            
            # Firmware Management Messages
            print("\n📋 FIRMWARE MANAGEMENT MESSAGES")
            print("=" * 35)
            await self.test_get_diagnostics()
            await asyncio.sleep(1)
            await self.test_update_firmware()
            
            # Local Authorization List Management
            print("\n📋 LOCAL AUTHORIZATION LIST MANAGEMENT")
            print("=" * 45)
            await self.test_get_local_list_version()
            await asyncio.sleep(1)
            await self.test_send_local_list()
            
            # Reservation Profile
            print("\n📋 RESERVATION PROFILE")
            print("=" * 25)
            await self.test_reserve_now()
            await asyncio.sleep(1)
            await self.test_cancel_reservation()
            
            # Remote Trigger Profile
            print("\n📋 REMOTE TRIGGER PROFILE")
            print("=" * 30)
            await self.test_change_availability()
            await asyncio.sleep(1)
            await self.test_change_configuration()
            await asyncio.sleep(1)
            await self.test_get_configuration()
            await asyncio.sleep(1)
            await self.test_remote_start_transaction()
            await asyncio.sleep(1)
            await self.test_remote_stop_transaction()
            await asyncio.sleep(1)
            await self.test_reset()
            await asyncio.sleep(1)
            await self.test_unlock_connector()
            
            # Data Transfer Profile
            print("\n📋 DATA TRANSFER PROFILE")
            print("=" * 30)
            await self.test_data_transfer()
            
            # Test Scenarios
            print("\n📋 TEST SCENARIOS")
            print("=" * 20)
            await self.test_complete_charging_session()
            await asyncio.sleep(2)
            await self.test_remote_control_session()
            
        finally:
            await self.disconnect()
        
        # Print summary
        self.print_test_summary()
    
    def print_test_summary(self):
        """Print test results summary"""
        print("\n" + "=" * 70)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 70)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["result"]["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for test in self.test_results:
                if not test["result"]["success"]:
                    print(f"  - {test['test_name']}: {test['result'].get('error', 'Unknown error')}")
        
        print("\n" + "=" * 70)

async def main():
    """Main function to run OCPP tests"""
    tester = OCPPTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
