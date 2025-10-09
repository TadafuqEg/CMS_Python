#!/usr/bin/env python3
"""
OCPP Master Socket Test
Tests master socket functionality for sending commands to chargers
"""

import asyncio
import ssl
import websockets
import json
from datetime import datetime, timezone

class OCPPMasterSocketTester:
    def __init__(self, server_url: str = "wss://localhost:9000"):
        self.server_url = server_url
        self.master_websocket = None
        self.charger_websocket = None
        self.test_rfid = "RFID123456789"
        self.test_connector_id = 1
        self.test_transaction_id = 12345
        
        # Create SSL context for testing
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        self.test_results = []
    
    async def connect_charger(self):
        """Connect charger to OCPP server"""
        try:
            self.charger_websocket = await websockets.connect(
                f"{self.server_url}/CP001",
                ssl=self.ssl_context,
                subprotocols=["ocpp1.6"]
            )
            print(f"✅ Charger connected to OCPP server: {self.server_url}/CP001")
            return True
        except Exception as e:
            print(f"❌ Failed to connect charger: {e}")
            return False
    
    async def connect_master(self):
        """Connect master socket to OCPP server"""
        try:
            self.master_websocket = await websockets.connect(
                f"{self.server_url}/master",
                ssl=self.ssl_context,
                subprotocols=["ocpp1.6"]
            )
            print(f"✅ Master socket connected to OCPP server: {self.server_url}/master")
            return True
        except Exception as e:
            print(f"❌ Failed to connect master socket: {e}")
            return False
    
    async def disconnect_all(self):
        """Disconnect all connections"""
        if self.charger_websocket:
            await self.charger_websocket.close()
            print("🔌 Charger disconnected")
        if self.master_websocket:
            await self.master_websocket.close()
            print("🔌 Master socket disconnected")
    
    async def send_charger_message(self, message: list, test_name: str) -> dict:
        """Send message from charger and wait for response"""
        try:
            message_json = json.dumps(message)
            print(f"📤 Charger {test_name}: {message_json}")
            
            await self.charger_websocket.send(message_json)
            
            # Wait for response
            response_json = await asyncio.wait_for(self.charger_websocket.recv(), timeout=10.0)
            response = json.loads(response_json)
            
            print(f"📥 Charger {test_name} Response: {response_json}")
            
            return {
                "success": True,
                "test_name": f"Charger {test_name}",
                "request": message,
                "response": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Charger {test_name}: Error - {e}")
            return {
                "success": False,
                "test_name": f"Charger {test_name}",
                "request": message,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def send_master_message(self, message: list, test_name: str) -> dict:
        """Send message from master socket and wait for feedback"""
        try:
            message_json = json.dumps(message)
            print(f"📤 Master {test_name}: {message_json}")
            
            await self.master_websocket.send(message_json)
            
            # Wait for feedback
            response_json = await asyncio.wait_for(self.master_websocket.recv(), timeout=10.0)
            response = json.loads(response_json)
            
            print(f"📥 Master {test_name} Feedback: {response_json}")
            
            return {
                "success": True,
                "test_name": f"Master {test_name}",
                "request": message,
                "response": response,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Master {test_name}: Error - {e}")
            return {
                "success": False,
                "test_name": f"Master {test_name}",
                "request": message,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def test_master_socket_functionality(self):
        """Test master socket functionality"""
        print("🔧 Testing OCPP Master Socket Functionality")
        print("=" * 60)
        
        # Connect charger first
        if not await self.connect_charger():
            return
        
        try:
            # Step 1: Charger sends BootNotification
            print("\n🚀 Step 1: Charger sends BootNotification")
            boot_msg = [2, "boot_001", "BootNotification", {
                "chargePointVendor": "Commercial MINI DC",
                "chargePointModel": "CMDC-60kW",
                "chargePointSerialNumber": "CMDC001234567",
                "chargeBoxSerialNumber": "BOX001234567",
                "firmwareVersion": "1.0.0"
            }]
            result = await self.send_charger_message(boot_msg, "BootNotification")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 2: Connect master socket
            print("\n🔗 Step 2: Connect master socket")
            if not await self.connect_master():
                return
            await asyncio.sleep(1)
            
            # Step 3: Master sends RemoteStartTransaction
            print("\n⚡ Step 3: Master sends RemoteStartTransaction")
            remote_start_msg = [2, "remote_start_001", "RemoteStartTransaction", {
                "connectorId": self.test_connector_id,
                "idTag": self.test_rfid
            }]
            result = await self.send_master_message(remote_start_msg, "RemoteStartTransaction")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 4: Check if charger received the message
            print("\n📥 Step 4: Check if charger received RemoteStartTransaction")
            try:
                charger_response = await asyncio.wait_for(self.charger_websocket.recv(), timeout=5.0)
                charger_data = json.loads(charger_response)
                print(f"📥 Charger received: {charger_response}")
                
                if len(charger_data) >= 3 and charger_data[2] == "RemoteStartTransaction":
                    print("✅ Charger successfully received RemoteStartTransaction!")
                    self.test_results.append({
                        "success": True,
                        "test_name": "Charger Received RemoteStartTransaction",
                        "response": charger_data,
                        "timestamp": datetime.now().isoformat()
                    })
                else:
                    print(f"❓ Unexpected charger response: {charger_data}")
                    self.test_results.append({
                        "success": False,
                        "test_name": "Charger Received RemoteStartTransaction",
                        "error": f"Unexpected response: {charger_data}",
                        "timestamp": datetime.now().isoformat()
                    })
                    
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for charger response")
                self.test_results.append({
                    "success": False,
                    "test_name": "Charger Received RemoteStartTransaction",
                    "error": "Timeout",
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                print(f"❌ Error receiving charger response: {e}")
                self.test_results.append({
                    "success": False,
                    "test_name": "Charger Received RemoteStartTransaction",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            
            # Step 5: Master sends RemoteStopTransaction
            print("\n🛑 Step 5: Master sends RemoteStopTransaction")
            remote_stop_msg = [2, "remote_stop_001", "RemoteStopTransaction", {
                "transactionId": self.test_transaction_id
            }]
            result = await self.send_master_message(remote_stop_msg, "RemoteStopTransaction")
            self.test_results.append(result)
            await asyncio.sleep(1)
            
            # Step 6: Check if charger received the stop message
            print("\n📥 Step 6: Check if charger received RemoteStopTransaction")
            try:
                charger_response = await asyncio.wait_for(self.charger_websocket.recv(), timeout=5.0)
                charger_data = json.loads(charger_response)
                print(f"📥 Charger received: {charger_response}")
                
                if len(charger_data) >= 3 and charger_data[2] == "RemoteStopTransaction":
                    print("✅ Charger successfully received RemoteStopTransaction!")
                    self.test_results.append({
                        "success": True,
                        "test_name": "Charger Received RemoteStopTransaction",
                        "response": charger_data,
                        "timestamp": datetime.now().isoformat()
                    })
                else:
                    print(f"❓ Unexpected charger response: {charger_data}")
                    self.test_results.append({
                        "success": False,
                        "test_name": "Charger Received RemoteStopTransaction",
                        "error": f"Unexpected response: {charger_data}",
                        "timestamp": datetime.now().isoformat()
                    })
                    
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for charger response")
                self.test_results.append({
                    "success": False,
                    "test_name": "Charger Received RemoteStopTransaction",
                    "error": "Timeout",
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                print(f"❌ Error receiving charger response: {e}")
                self.test_results.append({
                    "success": False,
                    "test_name": "Charger Received RemoteStopTransaction",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            
        finally:
            await self.disconnect_all()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary"""
        print("\n" + "=" * 60)
        print("📊 MASTER SOCKET TEST RESULTS")
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
        else:
            print("\n✅ ALL TESTS PASSED!")
            print("🎯 Master socket functionality is working correctly!")
        
        print("=" * 60)

async def main():
    """Main function to run master socket tests"""
    tester = OCPPMasterSocketTester()
    await tester.test_master_socket_functionality()

if __name__ == "__main__":
    asyncio.run(main())
