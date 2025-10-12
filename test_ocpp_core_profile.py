#!/usr/bin/env python3
"""
OCPP Core Profile Messages Test
Tests all Core Profile messages from OCPP 1.6 specification
"""

import asyncio
import ssl
import websockets
import json
from datetime import datetime, timezone

class OCPPCoreProfileTester:
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
    
    async def test_core_profile_messages(self):
        """Test all Core Profile messages"""
        print("🔧 Testing OCPP 1.6 Core Profile Messages")
        print("=" * 50)
        
        if not await self.connect():
            return
        
        try:
            # 1. BootNotification
            print("\n1️⃣ BootNotification")
            boot_msg = [2, "boot_001", "BootNotification", {
                "chargePointVendor": "Commercial MINI DC",
                "chargePointModel": "CMDC-60kW",
                "chargePointSerialNumber": "CMDC001234567",
                "chargeBoxSerialNumber": "BOX001234567",
                "firmwareVersion": "1.0.0"
            }]
            result = await self.send_message(boot_msg, "BootNotification")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 2. Authorize
            print("\n2️⃣ Authorize")
            auth_msg = [2, "auth_001", "Authorize", {
                "idTag": self.test_rfid
            }]
            result = await self.send_message(auth_msg, "Authorize")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 3. StartTransaction
            print("\n3️⃣ StartTransaction")
            start_msg = [2, "start_001", "StartTransaction", {
                "connectorId": self.test_connector_id,
                "idTag": self.test_rfid,
                "meterStart": 1000,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
            result = await self.send_message(start_msg, "StartTransaction")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 4. StopTransaction
            print("\n4️⃣ StopTransaction")
            stop_msg = [2, "stop_001", "StopTransaction", {
                "transactionId": self.test_transaction_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "meterStop": 1500,
                "reason": "Local"
            }]
            result = await self.send_message(stop_msg, "StopTransaction")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 5. Heartbeat
            print("\n5️⃣ Heartbeat")
            heartbeat_msg = [2, "heart_001", "Heartbeat", {}]
            result = await self.send_message(heartbeat_msg, "Heartbeat")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 6. StatusNotification
            print("\n6️⃣ StatusNotification")
            status_msg = [2, "status_001", "StatusNotification", {
                "connectorId": self.test_connector_id,
                "errorCode": "NoError",
                "status": "Available",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
            result = await self.send_message(status_msg, "StatusNotification")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # 7. MeterValues
            print("\n7️⃣ MeterValues")
            meter_msg = [2, "meter_001", "MeterValues", {
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
                            }
                        ]
                    }
                ]
            }]
            result = await self.send_message(meter_msg, "MeterValues")
            self.test_results.append(result)
            
        finally:
            await self.disconnect()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary"""
        print("\n" + "=" * 50)
        print("📊 CORE PROFILE TEST RESULTS")
        print("=" * 50)
        
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
        
        print("=" * 50)

async def main():
    """Main function to run Core Profile tests"""
    tester = OCPPCoreProfileTester()
    await tester.test_core_profile_messages()

if __name__ == "__main__":
    asyncio.run(main())
