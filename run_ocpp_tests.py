#!/usr/bin/env python3
"""
OCPP Test Suite Runner
Runs all OCPP 1.6 test suites from the Postman Testing Guide
"""

import asyncio
import sys
import os
from datetime import datetime

# Import all test modules
from test_ocpp_core_profile import OCPPCoreProfileTester
from test_ocpp_remote_trigger import OCPPRemoteTriggerTester
from test_ocpp_charging_session import OCPPChargingSessionTester

class OCPPTestSuiteRunner:
    def __init__(self, server_url: str = "wss://localhost:9000", charge_point_id: str = "CP001"):
        self.server_url = server_url
        self.charge_point_id = charge_point_id
        self.all_results = []
        
    async def run_all_tests(self):
        """Run all OCPP test suites"""
        print("🚀 OCPP 1.6 Comprehensive Test Suite Runner")
        print("=" * 70)
        print(f"Server: {self.server_url}")
        print(f"Charge Point ID: {self.charge_point_id}")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
        # Test 1: Core Profile Messages
        print("\n📋 TEST SUITE 1: CORE PROFILE MESSAGES")
        print("-" * 50)
        core_tester = OCPPCoreProfileTester(self.server_url, self.charge_point_id)
        await core_tester.test_core_profile_messages()
        self.all_results.extend(core_tester.test_results)
        
        await asyncio.sleep(2)  # Brief pause between test suites
        
        # Test 2: Remote Trigger Profile Messages
        print("\n📋 TEST SUITE 2: REMOTE TRIGGER PROFILE MESSAGES")
        print("-" * 50)
        remote_tester = OCPPRemoteTriggerTester(self.server_url, self.charge_point_id)
        await remote_tester.test_remote_trigger_messages()
        self.all_results.extend(remote_tester.test_results)
        
        await asyncio.sleep(2)  # Brief pause between test suites
        
        # Test 3: Complete Charging Session Scenario
        print("\n📋 TEST SUITE 3: COMPLETE CHARGING SESSION SCENARIO")
        print("-" * 50)
        session_tester = OCPPChargingSessionTester(self.server_url, self.charge_point_id)
        await session_tester.test_complete_charging_session()
        self.all_results.extend(session_tester.test_results)
        
        # Print overall summary
        self.print_overall_summary()
    
    def print_overall_summary(self):
        """Print overall test results summary"""
        print("\n" + "=" * 70)
        print("📊 OVERALL TEST RESULTS SUMMARY")
        print("=" * 70)
        
        total_tests = len(self.all_results)
        passed_tests = sum(1 for result in self.all_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
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
        
        print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

async def main():
    """Main function"""
    # Check if central system is running
    print("🔍 Checking if OCPP Central System is running...")
    
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
    
    # Run all tests
    runner = OCPPTestSuiteRunner(server_url, charge_point_id)
    await runner.run_all_tests()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Test suite interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        sys.exit(1)
