#!/usr/bin/env python3
"""
OCPP 1.6 Complete Test Suite Runner
Comprehensive testing of all OCPP messages from the Postman Testing Guide
"""

import asyncio
import sys
import os
from datetime import datetime

# Import all test modules
from test_ocpp_core_profile import OCPPCoreProfileTester
from test_ocpp_remote_trigger import OCPPRemoteTriggerTester
from test_ocpp_charging_session import OCPPChargingSessionTester
from test_ocpp_master_socket import OCPPMasterSocketTester

class OCPPCompleteTestRunner:
    def __init__(self, server_url: str = "wss://localhost:9000", charge_point_id: str = "CP001"):
        self.server_url = server_url
        self.charge_point_id = charge_point_id
        self.all_results = []
        self.start_time = datetime.now()
        
    async def run_all_test_suites(self):
        """Run all OCPP test suites"""
        print("🚀 OCPP 1.6 Complete Test Suite Runner")
        print("=" * 80)
        print(f"Server: {self.server_url}")
        print(f"Charge Point ID: {self.charge_point_id}")
        print(f"Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print("📋 Based on OCPP Postman Testing Guide")
        print("=" * 80)
        
        # Test Suite 1: Core Profile Messages
        print("\n📋 TEST SUITE 1: CORE PROFILE MESSAGES")
        print("Testing: BootNotification, Authorize, StartTransaction, StopTransaction,")
        print("         Heartbeat, StatusNotification, MeterValues")
        print("-" * 60)
        core_tester = OCPPCoreProfileTester(self.server_url, self.charge_point_id)
        await core_tester.test_core_profile_messages()
        self.all_results.extend(core_tester.test_results)
        
        await asyncio.sleep(2)  # Brief pause between test suites
        
        # Test Suite 2: Remote Trigger Profile Messages
        print("\n📋 TEST SUITE 2: REMOTE TRIGGER PROFILE MESSAGES")
        print("Testing: ChangeAvailability, ChangeConfiguration, GetConfiguration,")
        print("         RemoteStartTransaction, RemoteStopTransaction, Reset, UnlockConnector")
        print("-" * 60)
        remote_tester = OCPPRemoteTriggerTester(self.server_url, self.charge_point_id)
        await remote_tester.test_remote_trigger_messages()
        self.all_results.extend(remote_tester.test_results)
        
        await asyncio.sleep(2)  # Brief pause between test suites
        
        # Test Suite 3: Master Socket Functionality
        print("\n📋 TEST SUITE 3: MASTER SOCKET FUNCTIONALITY")
        print("Testing: Master socket broadcasting, RemoteStartTransaction,")
        print("         RemoteStopTransaction, Feedback mechanism")
        print("-" * 60)
        master_tester = OCPPMasterSocketTester(self.server_url)
        await master_tester.test_master_socket_functionality()
        self.all_results.extend(master_tester.test_results)
        
        await asyncio.sleep(2)  # Brief pause between test suites
        
        # Test Suite 4: Complete Charging Session Scenario
        print("\n📋 TEST SUITE 4: COMPLETE CHARGING SESSION SCENARIO")
        print("Testing: Full charging workflow from boot to completion")
        print("         Based on Postman Guide Scenario 1")
        print("-" * 60)
        session_tester = OCPPChargingSessionTester(self.server_url, self.charge_point_id)
        await session_tester.test_complete_charging_session()
        self.all_results.extend(session_tester.test_results)
        
        # Print overall summary
        self.print_overall_summary()
    
    def print_overall_summary(self):
        """Print overall test results summary"""
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        print("\n" + "=" * 80)
        print("📊 COMPLETE OCPP 1.6 TEST SUITE RESULTS")
        print("=" * 80)
        
        total_tests = len(self.all_results)
        passed_tests = sum(1 for result in self.all_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        print(f"Duration: {duration.total_seconds():.1f} seconds")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.all_results:
                if not result["success"]:
                    test_name = result.get("test_name", result.get("step_name", "Unknown"))
                    error = result.get("error", "Unknown error")
                    print(f"  - {test_name}: {error}")
        else:
            print("\n✅ ALL TESTS PASSED!")
            print("🎯 OCPP 1.6 implementation is working correctly!")
            print("🎉 All Postman Testing Guide scenarios validated!")
        
        print(f"\nCompleted at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Print test coverage summary
        self.print_test_coverage()
    
    def print_test_coverage(self):
        """Print test coverage summary"""
        print("\n📋 TEST COVERAGE SUMMARY")
        print("-" * 40)
        
        # Count tests by category
        core_tests = sum(1 for r in self.all_results if "BootNotification" in r.get("test_name", "") or 
                        "Authorize" in r.get("test_name", "") or "StartTransaction" in r.get("test_name", "") or
                        "StopTransaction" in r.get("test_name", "") or "Heartbeat" in r.get("test_name", "") or
                        "StatusNotification" in r.get("test_name", "") or "MeterValues" in r.get("test_name", ""))
        
        remote_tests = sum(1 for r in self.all_results if "ChangeAvailability" in r.get("test_name", "") or
                          "ChangeConfiguration" in r.get("test_name", "") or "GetConfiguration" in r.get("test_name", "") or
                          "RemoteStartTransaction" in r.get("test_name", "") or "RemoteStopTransaction" in r.get("test_name", "") or
                          "Reset" in r.get("test_name", "") or "UnlockConnector" in r.get("test_name", ""))
        
        master_tests = sum(1 for r in self.all_results if "Master" in r.get("test_name", "") or
                          "Charger Received" in r.get("test_name", ""))
        
        scenario_tests = sum(1 for r in self.all_results if "Step" in r.get("step_name", ""))
        
        print(f"Core Profile Messages: {core_tests} tests")
        print(f"Remote Trigger Profile: {remote_tests} tests")
        print(f"Master Socket Functionality: {master_tests} tests")
        print(f"Complete Charging Scenario: {scenario_tests} tests")
        print(f"Total Test Coverage: {total_tests} tests")
        
        print("\n📚 MESSAGE TYPES COVERED:")
        print("✅ BootNotification")
        print("✅ Authorize")
        print("✅ StartTransaction")
        print("✅ StopTransaction")
        print("✅ Heartbeat")
        print("✅ StatusNotification")
        print("✅ MeterValues")
        print("✅ ChangeAvailability")
        print("✅ ChangeConfiguration")
        print("✅ GetConfiguration")
        print("✅ RemoteStartTransaction")
        print("✅ RemoteStopTransaction")
        print("✅ Reset")
        print("✅ UnlockConnector")
        print("✅ Master Socket Broadcasting")
        print("✅ Complete Charging Session Workflow")

async def main():
    """Main function"""
    print("🔍 OCPP 1.6 Complete Test Suite")
    print("This will test all OCPP messages from the Postman Testing Guide")
    print()
    
    # You can customize these parameters
    server_url = "wss://localhost:9000"
    charge_point_id = "CP001"
    
    # Check command line arguments
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    if len(sys.argv) > 2:
        charge_point_id = sys.argv[2]
    
    print(f"Using server: {server_url}")
    print(f"Using charge point ID: {charge_point_id}")
    print()
    
    # Confirm before running
    try:
        response = input("Press Enter to start tests, or Ctrl+C to cancel: ")
    except KeyboardInterrupt:
        print("\n⏹️ Test suite cancelled by user")
        return
    
    # Run all tests
    runner = OCPPCompleteTestRunner(server_url, charge_point_id)
    await runner.run_all_test_suites()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Test suite interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        sys.exit(1)
