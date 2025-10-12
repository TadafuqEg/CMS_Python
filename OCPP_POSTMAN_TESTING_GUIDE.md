# OCPP 1.6 Postman Testing Guide

## Overview
This guide provides comprehensive documentation for testing OCPP 1.6 requests from charging stations using Postman. All examples are based on real charging station behavior and include proper message formatting, headers, and expected responses.

**Important**: OCPP 1.6 messages are sent as JSON arrays, not objects. The format is:
- **Request**: `[MessageType, MessageId, Action, RequestData]`
- **Response**: `[MessageType, MessageId, ResponseData]`

Where:
- `MessageType`: 2 for requests, 3 for responses
- `MessageId`: Unique identifier for the message
- `Action`: The OCPP action name
- `RequestData/ResponseData`: The actual data payload

## Table of Contents
1. [Setup](#setup)
2. [Core Profile Messages](#core-profile-messages)
3. [Firmware Management Messages](#firmware-management-messages)
4. [Local Authorization List Management](#local-authorization-list-management)
5. [Reservation Profile](#reservation-profile)
6. [Remote Trigger Profile](#remote-trigger-profile)
7. [Data Transfer Profile](#data-transfer-profile)
8. [Testing Scenarios](#testing-scenarios)
9. [Common Issues & Solutions](#common-issues--solutions)

## Setup

### Environment Variables
Create a Postman environment with these variables:
```json
{
  "ocpp_server_url": "ws://192.168.60.37:8083",
  "mobile_server_url": "ws://192.168.60.37:8081",
  "charge_point_id": "CP001",
  "test_rfid": "RFID123456789",
  "test_connector_id": "1",
  "test_transaction_id": "12345"
}
```

### Centralized WebSocket Server
The system uses a centralized WebSocket server (`websocket:serve-enhanced`) that handles both:
- **OCPP WebSocket connections** on port 8083
- **Mobile WebSocket connections** on port 8081

**Start the server:**
```bash
# Using artisan command
php artisan websocket:serve-enhanced --host=192.168.60.37 --ocpp-port=8083 --mobile-port=8081

# Or using the provided script
./start-websocket-server.sh  # Linux/Mac
start-websocket-server.bat    # Windows
```

### Headers
All OCPP requests require these headers:
```
Content-Type: application/json
User-Agent: OCPP-1.6-ChargePoint/1.0
```

## Core Profile Messages

### 1. BootNotification
**Purpose**: Sent by charging station when it boots up
**Direction**: Station → Central System

```json
[2, "boot_001", "BootNotification", {
  "chargePointVendor": "Commercial MINI DC",
  "chargePointModel": "CMDC-60kW",
  "chargePointSerialNumber": "CMDC001234567",
  "chargeBoxSerialNumber": "BOX001234567",
  "firmwareVersion": "1.0.0"
}]
```

**Expected Response**:
```json
[3, "boot_001", {
  "status": "Accepted",
  "currentTime": "2025-09-25T22:00:00+02:00",
  "interval": 300
}]
```

### 2. Authorize
**Purpose**: Request authorization for charging session
**Direction**: Station → Central System

```json
[2, "auth_001", "Authorize", {
  "idTag": "RFID123456789"
}]
```

**Expected Response**:
```json
[3, "auth_001", {
  "idTagInfo": {
    "status": "Accepted",
    "expiryDate": "2026-09-25T22:00:00+02:00"
  }
}]
```

### 3. StartTransaction
**Purpose**: Start a charging session
**Direction**: Station → Central System

```json
[2, "start_001", "StartTransaction", {
  "connectorId": 1,
  "idTag": "RFID123456789",
  "meterStart": 1000,
  "timestamp": "2025-09-25T22:00:00+02:00"
}]
```

**Expected Response**:
```json
[3, "start_001", {
  "transactionId": 12345,
  "idTagInfo": {
    "status": "Accepted"
  }
}]
```

### 4. StopTransaction
**Purpose**: Stop a charging session
**Direction**: Station → Central System

```json
[2, "stop_001", "StopTransaction", {
  "transactionId": 12345,
  "timestamp": "2025-09-25T22:30:00+02:00",
  "meterStop": 1500,
  "reason": "Local"
}]
```

**Expected Response**:
```json
[3, "stop_001", {
  "idTagInfo": {
    "status": "Accepted"
  }
}]
```

### 5. Heartbeat
**Purpose**: Keep connection alive
**Direction**: Station → Central System

```json
[2, "heart_001", "Heartbeat", {}]
```

**Expected Response**:
```json
[3, "heart_001", {
  "currentTime": "2025-09-25T22:00:00+02:00"
}]
```

### 6. StatusNotification
**Purpose**: Report connector status changes
**Direction**: Station → Central System

```json
[2, "status_001", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Available",
  "timestamp": "2025-09-25T22:00:00+02:00"
}]
```

**Expected Response**:
```json
[3, "status_001", {}]
```

### 7. MeterValues
**Purpose**: Report energy consumption data
**Direction**: Station → Central System

```json
[2, "meter_001", "MeterValues", {
  "connectorId": 1,
  "transactionId": 12345,
  "meterValue": [
    {
      "timestamp": "2025-09-25T22:00:00+02:00",
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
```

**Expected Response**:
```json
[3, "meter_001", {}]
```

## Firmware Management Messages

### 8. GetDiagnostics
**Purpose**: Request diagnostic data from station
**Direction**: Central System → Station

```json
[2, "diag_001", "GetDiagnostics", {
  "location": "http://192.168.60.37:8000/api/v1/diagnostics",
  "retries": 3,
  "retryInterval": 60
}]
```

**Expected Response**:
```json
[3, "diag_001", {
  "status": "Accepted"
}]
```

### 9. UpdateFirmware
**Purpose**: Update station firmware
**Direction**: Central System → Station

```json
[2, "fw_001", "UpdateFirmware", {
  "location": "http://192.168.60.37:8000/api/v1/firmware/update.bin",
  "retries": 3,
  "retryInterval": 60,
  "retrieveDate": "2025-09-25T22:00:00+02:00"
}]
```

**Expected Response**:
```json
[3, "fw_001", {
  "status": "Accepted"
}]
```

## Local Authorization List Management

### 10. GetLocalListVersion
**Purpose**: Get version of local authorization list
**Direction**: Central System → Station

```json
[2, "list_001", "GetLocalListVersion", {}]
```

**Expected Response**:
```json
[3, "list_001", {
  "listVersion": 1
}]
```

### 11. SendLocalList
**Purpose**: Update local authorization list
**Direction**: Central System → Station

```json
[2, "send_001", "SendLocalList", {
  "listVersion": 1,
  "updateType": "Full",
  "localAuthorizationList": [
    {
      "idTag": "RFID123456789",
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
```

**Expected Response**:
```json
[3, "send_001", {
  "status": "Accepted"
}]
```

## Reservation Profile

### 12. ReserveNow
**Purpose**: Reserve a connector
**Direction**: Central System → Station

```json
[2, "reserve_001", "ReserveNow", {
  "connectorId": 1,
  "expiryDate": "2025-09-25T23:00:00+02:00",
  "idTag": "RFID123456789",
  "reservationId": 12345
}]
```

**Expected Response**:
```json
[3, "reserve_001", {
  "status": "Accepted"
}]
```

### 13. CancelReservation
**Purpose**: Cancel a reservation
**Direction**: Central System → Station

```json
[2, "cancel_001", "CancelReservation", {
  "reservationId": 12345
}]
```

**Expected Response**:
```json
[3, "cancel_001", {
  "status": "Accepted"
}]
```

## Remote Trigger Profile

### 14. ChangeAvailability
**Purpose**: Change connector availability
**Direction**: Central System → Station

```json
[2, "avail_001", "ChangeAvailability", {
  "connectorId": 1,
  "type": "Operative"
}]
```

**Expected Response**:
```json
[3, "avail_001", {
  "status": "Accepted"
}]
```

### 15. ChangeConfiguration
**Purpose**: Change station configuration
**Direction**: Central System → Station

```json
[2, "config_001", "ChangeConfiguration", {
  "key": "HeartbeatInterval",
  "value": "300"
}]
```

**Expected Response**:
```json
[3, "config_001", {
  "status": "Accepted"
}]
```

### 16. GetConfiguration
**Purpose**: Get station configuration
**Direction**: Central System → Station

```json
[2, "getconfig_001", "GetConfiguration", {
  "key": ["HeartbeatInterval", "MeterValueSampleInterval"]
}]
```

**Expected Response**:
```json
[3, "getconfig_001", {
  "configurationKey": [
    {
      "key": "HeartbeatInterval",
      "readonly": false,
      "value": "300"
    },
    {
      "key": "MeterValueSampleInterval",
      "readonly": false,
      "value": "60"
    }
  ],
  "unknownKey": []
}]
```

### 17. RemoteStartTransaction
**Purpose**: Remotely start a transaction
**Direction**: Central System → Station

```json
[2, "remote_start_001", "RemoteStartTransaction", {
  "connectorId": 1,
  "idTag": "RFID123456789"
}]
```

**Expected Response**:
```json
[3, "remote_start_001", {
  "status": "Accepted"
}]
```

### 18. RemoteStopTransaction
**Purpose**: Remotely stop a transaction
**Direction**: Central System → Station

```json
[2, "remote_stop_001", "RemoteStopTransaction", {
  "transactionId": 12345
}]
```

**Expected Response**:
```json
[3, "remote_stop_001", {
  "status": "Accepted"
}]
```

### 19. Reset
**Purpose**: Reset the station
**Direction**: Central System → Station

```json
[2, "reset_001", "Reset", {
  "type": "Hard"
}]
```

**Expected Response**:
```json
[3, "reset_001", {
  "status": "Accepted"
}]
```

### 20. UnlockConnector
**Purpose**: Unlock a connector
**Direction**: Central System → Station

```json
[2, "unlock_001", "UnlockConnector", {
  "connectorId": 1
}]
```

**Expected Response**:
```json
[3, "unlock_001", {
  "status": "Unlocked"
}]
```

## Data Transfer Profile

### 21. DataTransfer
**Purpose**: Exchange custom data
**Direction**: Bidirectional

```json
[2, "data_001", "DataTransfer", {
  "vendorId": "Commercial MINI DC",
  "messageId": "CustomMessage",
  "data": "Custom data payload"
}]
```

**Expected Response**:
```json
[3, "data_001", {
  "status": "Accepted",
  "data": "Response data"
}]
```

## Testing Scenarios

### Scenario 1: Complete Charging Session
1. **BootNotification** - Station boots up
2. **StatusNotification** - Connector becomes available
3. **Authorize** - User presents RFID card
4. **StartTransaction** - Charging begins
5. **MeterValues** - Periodic energy reports (every 60 seconds)
6. **StatusNotification** - Connector status changes to "Charging"
7. **StopTransaction** - Charging ends
8. **StatusNotification** - Connector becomes available again

### Scenario 2: Remote Control Session
1. **BootNotification** - Station boots up
2. **GetConfiguration** - Get current settings
3. **ChangeConfiguration** - Update heartbeat interval
4. **RemoteStartTransaction** - Start charging remotely
5. **MeterValues** - Monitor charging progress
6. **RemoteStopTransaction** - Stop charging remotely

### Scenario 3: Error Handling
1. **BootNotification** - Station boots up
2. **StatusNotification** - Connector faulted
3. **Authorize** - Invalid RFID card
4. **StartTransaction** - Transaction rejected
5. **StatusNotification** - Connector unavailable

## Common Issues & Solutions

### Issue 1: Connection Refused
**Problem**: Cannot connect to OCPP server
**Solution**: 
- Verify server is running on correct IP/port
- Check firewall settings
- Ensure WebSocket endpoint is accessible

### Issue 2: Invalid Message Format
**Problem**: Server returns "Invalid message format"
**Solution**:
- Check JSON syntax
- Verify required fields are present
- Ensure timestamp format is ISO 8601

### Issue 3: Authentication Failed
**Problem**: Authorize request returns "Invalid"
**Solution**:
- Verify RFID card is in authorization list
- Check card expiry date
- Ensure proper card format

### Issue 4: Transaction Already Active
**Problem**: StartTransaction fails with "Transaction already active"
**Solution**:
- Check if previous transaction was properly stopped
- Verify connector status
- Use RemoteStopTransaction if needed

## Status Values Reference

### Connector Status
- `Available` - Ready for charging
- `Preparing` - Preparing for charging
- `Charging` - Currently charging
- `SuspendedEV` - Suspended by EV
- `SuspendedEVSE` - Suspended by station
- `Finishing` - Finishing charging
- `Reserved` - Reserved for specific user
- `Unavailable` - Not available
- `Faulted` - Error condition

### Error Codes
- `NoError` - No error
- `ConnectorLockFailure` - Connector lock failed
- `EVCommunicationError` - Communication with EV failed
- `GroundFailure` - Ground fault detected
- `HighTemperature` - High temperature detected
- `InternalError` - Internal error
- `LocalListConflict` - Local list conflict
- `OtherError` - Other error
- `OverCurrentFailure` - Overcurrent detected
- `PowerMeterFailure` - Power meter failure
- `PowerSwitchFailure` - Power switch failure
- `ReaderFailure` - RFID reader failure
- `ResetFailure` - Reset failed
- `UnderVoltage` - Under voltage
- `OverVoltage` - Over voltage
- `WeakSignal` - Weak signal

### Stop Reasons
- `EmergencyStop` - Emergency stop
- `EVDisconnected` - EV disconnected
- `HardReset` - Hard reset
- `Local` - Local stop
- `Other` - Other reason
- `PowerLoss` - Power loss
- `Reboot` - Reboot
- `Remote` - Remote stop
- `SoftReset` - Soft reset
- `UnlockCommand` - Unlock command
- `DeAuthorized` - Deauthorized

## Configuration Keys Reference

### Common Configuration Keys
- `HeartbeatInterval` - Heartbeat interval in seconds (default: 300)
- `MeterValueSampleInterval` - Meter sampling interval in seconds (default: 60)
- `NumberOfConnectors` - Number of connectors (default: 1)
- `AllowOfflineTxForUnknownId` - Allow offline transactions (default: false)
- `AuthorizationCacheEnabled` - Enable authorization cache (default: false)
- `ConnectionTimeOut` - Connection timeout in seconds (default: 60)
- `ResetRetries` - Number of reset retries (default: 3)
- `StopTransactionOnEVSideDisconnect` - Stop on EV disconnect (default: true)
- `UnlockConnectorOnEVSideDisconnect` - Unlock on EV disconnect (default: false)

## Postman Collection Import

To import this collection into Postman:

1. Create a new collection named "OCPP 1.6 Testing"
2. Add environment variables as specified above
3. Create requests for each message type
4. Use the JSON examples provided
5. Set up pre-request scripts for dynamic values
6. Add tests to validate responses

## Testing Checklist

- [ ] BootNotification works
- [ ] Authorize with valid RFID
- [ ] Authorize with invalid RFID
- [ ] StartTransaction with valid authorization
- [ ] StartTransaction without authorization
- [ ] StopTransaction with valid transaction
- [ ] Heartbeat every 5 minutes
- [ ] StatusNotification for all status changes
- [ ] MeterValues with various measurands
- [ ] RemoteStartTransaction
- [ ] RemoteStopTransaction
- [ ] ChangeConfiguration
- [ ] GetConfiguration
- [ ] Reset (Hard and Soft)
- [ ] UnlockConnector
- [ ] ReserveNow
- [ ] CancelReservation
- [ ] SendLocalList
- [ ] GetLocalListVersion
- [ ] DataTransfer
- [ ] Error handling for all messages

## Notes

- **OCPP Message Format**: All OCPP 1.6 messages are JSON arrays: `[MessageType, MessageId, Action, RequestData]` for requests and `[MessageType, MessageId, ResponseData]` for responses
- All timestamps must be in ISO 8601 format
- MessageId must be unique for each request
- ConnectorId 0 refers to the station itself
- TransactionId is generated by the station
- ReservationId is generated by the central system
- Test with real charging stations when possible
- Monitor logs for debugging
- Use proper error handling in tests
