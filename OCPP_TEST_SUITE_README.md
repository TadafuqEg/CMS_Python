# OCPP 1.6 Test Suite

This directory contains comprehensive test suites for OCPP 1.6 Central Management System based on the Postman Testing Guide.

## Test Files Overview

### Individual Test Suites

1. **`test_ocpp_core_profile.py`** - Tests Core Profile messages
   - BootNotification
   - Authorize
   - StartTransaction
   - StopTransaction
   - Heartbeat
   - StatusNotification
   - MeterValues

2. **`test_ocpp_remote_trigger.py`** - Tests Remote Trigger Profile messages
   - ChangeAvailability
   - ChangeConfiguration
   - GetConfiguration
   - RemoteStartTransaction
   - RemoteStopTransaction
   - Reset
   - UnlockConnector

3. **`test_ocpp_charging_session.py`** - Tests complete charging session scenario
   - Full workflow from boot to completion
   - Based on Postman Guide Scenario 1

4. **`test_ocpp_master_socket.py`** - Tests master socket functionality
   - Master socket broadcasting
   - RemoteStartTransaction from master
   - RemoteStopTransaction from master
   - Feedback mechanism

### Comprehensive Test Suites

5. **`ocpp_comprehensive_tests.py`** - Complete test suite with all OCPP messages
   - All Core Profile messages
   - All Firmware Management messages
   - All Local Authorization List Management messages
   - All Reservation Profile messages
   - All Remote Trigger Profile messages
   - All Data Transfer Profile messages
   - Complete charging session scenarios

6. **`run_ocpp_tests.py`** - Test runner for individual suites
   - Runs Core Profile, Remote Trigger, and Charging Session tests
   - Provides overall summary

7. **`run_complete_ocpp_tests.py`** - Complete test runner
   - Runs all test suites including master socket functionality
   - Comprehensive coverage report
   - Detailed test results summary

## Prerequisites

1. **OCPP Central System Running**: Make sure `central_system.py` is running
   ```bash
   python central_system.py
   ```

2. **Python Dependencies**: Ensure required packages are installed
   ```bash
   pip install websockets asyncio ssl
   ```

## Usage

### Run Individual Test Suites

```bash
# Test Core Profile messages only
python test_ocpp_core_profile.py

# Test Remote Trigger Profile messages only
python test_ocpp_remote_trigger.py

# Test complete charging session scenario
python test_ocpp_charging_session.py

# Test master socket functionality
python test_ocpp_master_socket.py
```

### Run Comprehensive Test Suites

```bash
# Run all individual test suites with summary
python run_ocpp_tests.py

# Run complete test suite with all functionality
python run_complete_ocpp_tests.py

# Run comprehensive test with all OCPP messages
python ocpp_comprehensive_tests.py
```

### Customize Server Settings

You can specify custom server URL and charge point ID:

```bash
# Use custom server URL
python run_complete_ocpp_tests.py wss://192.168.1.100:9000

# Use custom server URL and charge point ID
python run_complete_ocpp_tests.py wss://192.168.1.100:9000 CP002
```

## Test Results

Each test suite provides:
- ✅ **Passed tests** - Messages sent and received correctly
- ❌ **Failed tests** - Messages that failed with error details
- 📊 **Success rate** - Percentage of tests that passed
- ⏱️ **Duration** - Time taken to complete all tests

## Message Coverage

The test suites cover all OCPP 1.6 messages from the Postman Testing Guide:

### Core Profile Messages
- ✅ BootNotification
- ✅ Authorize
- ✅ StartTransaction
- ✅ StopTransaction
- ✅ Heartbeat
- ✅ StatusNotification
- ✅ MeterValues

### Firmware Management Messages
- ✅ GetDiagnostics
- ✅ UpdateFirmware

### Local Authorization List Management
- ✅ GetLocalListVersion
- ✅ SendLocalList

### Reservation Profile
- ✅ ReserveNow
- ✅ CancelReservation

### Remote Trigger Profile
- ✅ ChangeAvailability
- ✅ ChangeConfiguration
- ✅ GetConfiguration
- ✅ RemoteStartTransaction
- ✅ RemoteStopTransaction
- ✅ Reset
- ✅ UnlockConnector

### Data Transfer Profile
- ✅ DataTransfer

### Master Socket Functionality
- ✅ Master socket broadcasting
- ✅ Feedback mechanism
- ✅ Remote command delivery

## Test Scenarios

### Scenario 1: Complete Charging Session
1. BootNotification - Station boots up
2. StatusNotification - Connector becomes available
3. Authorize - User presents RFID card
4. StartTransaction - Charging begins
5. MeterValues - Periodic energy reports
6. StatusNotification - Connector status changes to "Charging"
7. StopTransaction - Charging ends
8. StatusNotification - Connector becomes available again

### Scenario 2: Remote Control Session
1. BootNotification - Station boots up
2. GetConfiguration - Get current settings
3. ChangeConfiguration - Update heartbeat interval
4. RemoteStartTransaction - Start charging remotely
5. MeterValues - Monitor charging progress
6. RemoteStopTransaction - Stop charging remotely

### Scenario 3: Master Socket Broadcasting
1. Charger connects and sends BootNotification
2. Master socket connects
3. Master sends RemoteStartTransaction
4. Charger receives and processes the command
5. Master receives feedback about delivery status
6. Master sends RemoteStopTransaction
7. Charger receives and processes the stop command

## Troubleshooting

### Common Issues

1. **Connection Refused**
   - Ensure `central_system.py` is running
   - Check if port 9000 is available
   - Verify SSL certificates are present

2. **Timeout Errors**
   - Check network connectivity
   - Verify server is responding
   - Increase timeout values if needed

3. **InternalError Responses**
   - Some messages may return InternalError if handlers are not fully implemented
   - This is normal for testing purposes
   - The important thing is that messages are received and processed

4. **SSL Certificate Issues**
   - Tests use self-signed certificates for development
   - Certificate verification is disabled for testing
   - In production, use proper SSL certificates

### Debug Mode

To see detailed logs from the central system, run it with debug logging:

```bash
# Modify central_system.py logging level to DEBUG
# Then run the central system
python central_system.py
```

## Expected Results

When all tests pass, you should see:
- ✅ All Core Profile messages working
- ✅ All Remote Trigger Profile messages working
- ✅ Master socket broadcasting working
- ✅ Complete charging session scenarios working
- 📊 100% success rate (or close to it)
- 🎯 OCPP 1.6 implementation validated

## Notes

- Tests are designed to work with the OCPP 1.6 Central Management System
- All message formats follow OCPP 1.6 JSON specification
- Tests include proper error handling and timeout management
- Results are logged with timestamps for debugging
- Test suites can be run individually or together
- Master socket functionality includes feedback mechanism
- Complete charging session tests real-world scenarios

## Contributing

To add new tests:
1. Create a new test file following the existing pattern
2. Import required modules (asyncio, websockets, ssl, json)
3. Create a test class with connect/disconnect methods
4. Add test methods for specific OCPP messages
5. Include proper error handling and result logging
6. Update this README with new test information
