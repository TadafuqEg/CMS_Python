#!/usr/bin/env python3
"""
OCPP Remote Trigger Profile Messages Test
Tests all Remote Trigger Profile messages from OCPP 1.6 specification
"""

import asyncio
import ssl
import websockets
import json
from datetime import datetime, timezone

class OCPPRemoteTriggerTester:
    def __init__(self, server_url: str = "wss://localhost:9000", charge_point_id: str = "CP001"):
        self.server_url = server_url
        self.charge_point_id = charge_point_id
        self.websocket = None
        self.test_rfid = "RFID123456789"
        self.test_connector_id = 1
        self.test_transaction_id = 12345
        
        # Create SSL context for testing
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
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
    
    async def send_message(self, message: list, test_name: str) -> dict:
        """Send OCPP message and wait for response"""
        try:
            message_json = json.dumps(message)
            print(f"📤 {test_name}: {message_json}")
            
            await self.websocket.send(message_json)
            
            # Wait for response
            response_json = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            response = json.loads(response_json)
            
            print(f"📥 {test_name} Response: {response_json}")
            
            return {
                "success": True,
                "test_name": test_name,
                "request": message,
                "response": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except asyncio.TimeoutError:
            print(f"⏰ {test_name}: Timeout waiting for response")
            return {
                "success": False,
                "test_name": test_name,
                "request": message,
                "error": "Timeout",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"❌ {test_name}: Error - {e}")
            return {
                "success": False,
                "test_name": test_name,
                "request": message,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def test_remote_trigger_messages(self):
        """Test all Remote Trigger Profile messages"""
        print("🔧 Testing OCPP 1.6 Remote Trigger Profile Messages")
        print("=" * 60)
        
        if not await self.connect():
            return
        
        try:
            # First send BootNotification to establish connection
            print("\n🔌 Establishing connection with BootNotification")
            boot_msg = [2, "boot_001", "BootNotification", {
                "chargePointVendor": "Commercial MINI DC",
                "chargePointModel": "CMDC-60kW",
                "chargePointSerialNumber": "CMDC001234567",
                "chargeBoxSerialNumber": "BOX001234567",
                "firmwareVersion": "1.0.0"
            }]
            await self.send_message(boot_msg, "BootNotification")
            await asyncio.sleep(1)
            
            # 1. ChangeAvailability
            print("\n1️⃣ ChangeAvailability")
            avail_msg = [2, "avail_001", "ChangeAvailability", {
                "connectorId": self.test_connector_id,
                "type": "Operative"
            }]
            result = await self.send_message(avail_msg, "ChangeAvailability")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 2. ChangeConfiguration
            print("\n2️⃣ ChangeConfiguration")
            config_msg = [2, "config_001", "ChangeConfiguration", {
                "key": "HeartbeatInterval",
                "value": "300"
            }]
            result = await self.send_message(config_msg, "ChangeConfiguration")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 3. GetConfiguration
            print("\n3️⃣ GetConfiguration")
            getconfig_msg = [2, "getconfig_001", "GetConfiguration", {
                "key": ["HeartbeatInterval", "MeterValueSampleInterval"]
            }]
            result = await self.send_message(getconfig_msg, "GetConfiguration")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 4. RemoteStartTransaction
            print("\n4️⃣ RemoteStartTransaction")
            remote_start_msg = [2, "remote_start_001", "RemoteStartTransaction", {
                "connectorId": self.test_connector_id,
                "idTag": self.test_rfid
            }]
            result = await self.send_message(remote_start_msg, "RemoteStartTransaction")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 5. RemoteStopTransaction
            print("\n5️⃣ RemoteStopTransaction")
            remote_stop_msg = [2, "remote_stop_001", "RemoteStopTransaction", {
                "transactionId": self.test_transaction_id
            }]
            result = await self.send_message(remote_stop_msg, "RemoteStopTransaction")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 6. Reset
            print("\n6️⃣ Reset")
            reset_msg = [2, "reset_001", "Reset", {
                "type": "Hard"
            }]
            result = await self.send_message(reset_msg, "Reset")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 7. UnlockConnector
            print("\n7️⃣ UnlockConnector")
            unlock_msg = [2, "unlock_001", "UnlockConnector", {
                "connectorId": self.test_connector_id
            }]
            result = await self.send_message(unlock_msg, "UnlockConnector")
            self.test_results.append(result)
            
        finally:
            await self.disconnect()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary"""
        print("\n" + "=" * 60)
        print("📊 REMOTE TRIGGER PROFILE TEST RESULTS")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test_name']}: {result.get('error', 'Unknown error')}")
        
        print("=" * 60)

async def main():
    """Main function to run Remote Trigger Profile tests"""
    tester = OCPPRemoteTriggerTester()
    await tester.test_remote_trigger_messages()

if __name__ == "__main__":
    asyncio.run(main())
