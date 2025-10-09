#!/usr/bin/env python3
"""
OCPP Complete Charging Session Test
Tests a complete charging session scenario as described in the Postman guide
"""

import asyncio
import ssl
import websockets
import json
from datetime import datetime, timezone

class OCPPChargingSessionTester:
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
    
    async def send_message(self, message: list, step_name: str) -> dict:
        """Send OCPP message and wait for response"""
        try:
            message_json = json.dumps(message)
            print(f"📤 {step_name}: {message_json}")
            
            await self.websocket.send(message_json)
            
            # Wait for response
            response_json = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            response = json.loads(response_json)
            
            print(f"📥 {step_name} Response: {response_json}")
            
            return {
                "success": True,
                "step_name": step_name,
                "request": message,
                "response": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except asyncio.TimeoutError:
            print(f"⏰ {step_name}: Timeout waiting for response")
            return {
                "success": False,
                "step_name": step_name,
                "request": message,
                "error": "Timeout",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"❌ {step_name}: Error - {e}")
            return {
                "success": False,
                "step_name": step_name,
                "request": message,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def test_complete_charging_session(self):
        """Test complete charging session scenario"""
        print("🔧 Testing Complete OCPP Charging Session Scenario")
        print("=" * 60)
        print("Based on Postman Testing Guide - Scenario 1")
        print("=" * 60)
        
        if not await self.connect():
            return
        
        try:
            # Step 1: BootNotification - Station boots up
            print("\n🚀 Step 1: BootNotification - Station boots up")
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
            
            # Step 2: StatusNotification - Connector becomes available
            print("\n🔌 Step 2: StatusNotification - Connector becomes available")
            status_msg = [2, "status_001", "StatusNotification", {
                "connectorId": self.test_connector_id,
                "errorCode": "NoError",
                "status": "Available",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
            result = await self.send_message(status_msg, "StatusNotification (Available)")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 3: Authorize - User presents RFID card
            print("\n💳 Step 3: Authorize - User presents RFID card")
            auth_msg = [2, "auth_001", "Authorize", {
                "idTag": self.test_rfid
            }]
            result = await self.send_message(auth_msg, "Authorize")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 4: StartTransaction - Charging begins
            print("\n⚡ Step 4: StartTransaction - Charging begins")
            start_msg = [2, "start_001", "StartTransaction", {
                "connectorId": self.test_connector_id,
                "idTag": self.test_rfid,
                "meterStart": 1000,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
            result = await self.send_message(start_msg, "StartTransaction")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 5: MeterValues - Periodic energy reports (every 60 seconds)
            print("\n📊 Step 5: MeterValues - Periodic energy reports")
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
            result = await self.send_message(meter_msg, "MeterValues")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 6: StatusNotification - Connector status changes to "Charging"
            print("\n🔋 Step 6: StatusNotification - Connector status changes to 'Charging'")
            charging_status_msg = [2, "status_002", "StatusNotification", {
                "connectorId": self.test_connector_id,
                "errorCode": "NoError",
                "status": "Charging",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
            result = await self.send_message(charging_status_msg, "StatusNotification (Charging)")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 7: Additional MeterValues during charging
            print("\n📊 Step 7: Additional MeterValues during charging")
            meter_msg_2 = [2, "meter_002", "MeterValues", {
                "connectorId": self.test_connector_id,
                "transactionId": self.test_transaction_id,
                "meterValue": [
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "sampledValue": [
                            {
                                "value": "2000",
                                "context": "Sample.Periodic",
                                "format": "Raw",
                                "measurand": "Energy.Active.Import.Register",
                                "unit": "Wh"
                            },
                            {
                                "value": "8.2",
                                "context": "Sample.Periodic",
                                "format": "Raw",
                                "measurand": "Power.Active.Import",
                                "unit": "kW"
                            }
                        ]
                    }
                ]
            }]
            result = await self.send_message(meter_msg_2, "MeterValues (During Charging)")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 8: StopTransaction - Charging ends
            print("\n🛑 Step 8: StopTransaction - Charging ends")
            stop_msg = [2, "stop_001", "StopTransaction", {
                "transactionId": self.test_transaction_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "meterStop": 2500,
                "reason": "Local"
            }]
            result = await self.send_message(stop_msg, "StopTransaction")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 9: StatusNotification - Connector becomes available again
            print("\n✅ Step 9: StatusNotification - Connector becomes available again")
            available_status_msg = [2, "status_003", "StatusNotification", {
                "connectorId": self.test_connector_id,
                "errorCode": "NoError",
                "status": "Available",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
            result = await self.send_message(available_status_msg, "StatusNotification (Available Again)")
            self.test_results.append(result)
            
            print("\n🎉 Complete charging session scenario completed!")
            
        finally:
            await self.disconnect()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary"""
        print("\n" + "=" * 60)
        print("📊 COMPLETE CHARGING SESSION TEST RESULTS")
        print("=" * 60)
        
        total_steps = len(self.test_results)
        passed_steps = sum(1 for result in self.test_results if result["success"])
        failed_steps = total_steps - passed_steps
        
        print(f"Total Steps: {total_steps}")
        print(f"Passed: {passed_steps}")
        print(f"Failed: {failed_steps}")
        print(f"Success Rate: {(passed_steps/total_steps)*100:.1f}%")
        
        if failed_steps > 0:
            print("\n❌ FAILED STEPS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['step_name']}: {result.get('error', 'Unknown error')}")
        else:
            print("\n✅ All steps completed successfully!")
            print("🎯 Complete charging session scenario PASSED!")
        
        print("=" * 60)

async def main():
    """Main function to run complete charging session test"""
    tester = OCPPChargingSessionTester()
    await tester.test_complete_charging_session()

if __name__ == "__main__":
    asyncio.run(main())
