# OCPP Charging Flow Documentation

This document describes the complete charging flow between the CMS (Charge Management System) and the Charger using OCPP (Open Charge Point Protocol) messages.

## Overview

The charging flow consists of five main phases:
1. **Remote Start Transaction** - CMS initiates charging remotely
2. **Start Transaction** - Charger confirms transaction start
3. **Meter Values** - Charger sends periodic meter readings
4. **Remote Stop Transaction** - CMS initiates charging stop
5. **Stop Transaction** - Charger confirms transaction end

All messages follow the OCPP JSON format:
- **CALL (Type 2)**: `[2, messageId, action, payload]`
- **CALLRESULT (Type 3)**: `[3, messageId, payload]`

---

## 1. Remote Start Transaction

### Phase 1.1: CMS → Charger (Remote Start Request)

The CMS initiates a remote start transaction by sending a `RemoteStartTransaction` command to the charger.

**Message Format:**
```json
[2, "eb20dcf0-00a1-4275-bbb8-d00c26b4172a", "RemoteStartTransaction", {
  "connectorId": 1,
  "idTag": "RFID-0000000118"
}]
```

**Message Components:**
- **Type**: `2` (CALL)
- **Message ID**: `"eb20dcf0-00a1-4275-bbb8-d00c26b4172a"` (unique identifier)
- **Action**: `"RemoteStartTransaction"`
- **Payload**:
  - `connectorId`: The connector number where charging should start (integer)
  - `idTag`: RFID tag identifier for authorization (string)

### Phase 1.2: Charger → CMS (Remote Start Response)

The charger responds with the status of the remote start request.

**Message Format:**
```json
[3, "remote_start_001", {
  "status": "Accepted"
}]
```

**Message Components:**
- **Type**: `3` (CALLRESULT)
- **Message ID**: `"remote_start_001"` (matches the original request ID)
- **Payload**:
  - `status`: Status of the remote start request
    - `"Accepted"` - Request accepted, charging will start
    - `"Rejected"` - Request rejected (e.g., connector unavailable, invalid RFID)

---

## 2. Start Transaction

### Phase 2.1: Charger → CMS (Start Transaction Request)

After accepting the remote start, the charger initiates the actual transaction by sending a `StartTransaction` message.

**Message Format:**
```json
[2, "start_001", "StartTransaction", {
  "connectorId": 1,
  "idTag": "RFID001",
  "meterStart": 0,
  "reservationId": 0,
  "timestamp": "2025-11-29T10:12:48+02:00"
}]
```

**Message Components:**
- **Type**: `2` (CALL)
- **Message ID**: `"start_001"` (unique identifier)
- **Action**: `"StartTransaction"`
- **Payload**:
  - `connectorId`: Connector number where transaction started (integer)
  - `idTag`: RFID tag used for authorization (string)
  - `meterStart`: Initial meter reading in Wh (integer, 0 if not available)
  - `reservationId`: Reservation ID if transaction is part of a reservation (integer, 0 if none)
  - `timestamp`: ISO 8601 timestamp when transaction started (string)

### Phase 2.2: CMS → Charger (Start Transaction Response)

The CMS responds with transaction details and authorization status.

**Message Format:**
```json
[3, "start_001", {
  "transactionId": 9,
  "idTagInfo": {
    "status": "Accepted"
  }
}]
```

**Message Components:**
- **Type**: `3` (CALLRESULT)
- **Message ID**: `"start_001"` (matches the request ID)
- **Payload**:
  - `transactionId`: Unique transaction identifier assigned by CMS (integer)
  - `idTagInfo`: Authorization information
    - `status`: Authorization status
      - `"Accepted"` - RFID tag is authorized
      - `"Blocked"` - RFID tag is blocked
      - `"Expired"` - RFID tag has expired
      - `"Invalid"` - RFID tag is invalid
      - `"ConcurrentTx"` - RFID tag already has an active transaction

---

## 3. Meter Values

### Phase 3.1: Charger → CMS (Meter Values Request)

During the charging session, the charger periodically sends meter readings to the CMS.

**Message Format:**
```json
[2, "meter_001", "MeterValues", {
  "connectorId": 1,
  "transactionId": 9,
  "meterValue": [{
    "timestamp": "2025-11-29T10:15:07+02:00",
    "sampledValue": [
      {
        "value": "0",
        "context": "Sample.Periodic",
        "format": "Raw",
        "measurand": "Energy.Active.Import.Register",
        "location": "Outlet",
        "unit": "Wh"
      },
      {
        "value": "38234",
        "context": "Sample.Periodic",
        "format": "Raw",
        "measurand": "Power.Active.Import",
        "location": "Outlet",
        "unit": "W"
      },
      {
        "value": "38000",
        "context": "Sample.Periodic",
        "format": "Raw",
        "measurand": "Power.Offered",
        "location": "Outlet",
        "unit": "W"
      },
      {
        "value": "100.50",
        "context": "Sample.Periodic",
        "format": "Raw",
        "measurand": "Current.Import",
        "location": "Outlet",
        "unit": "A"
      },
      {
        "value": "380.2",
        "context": "Sample.Periodic",
        "format": "Raw",
        "measurand": "Voltage",
        "location": "Outlet",
        "unit": "V"
      },
      {
        "value": "27.0",
        "context": "Sample.Periodic",
        "format": "Raw",
        "measurand": "Temperature",
        "location": "Cable",
        "unit": "Celsius"
      },
      {
        "value": "67",
        "context": "Transaction.Begin",
        "format": "Raw",
        "measurand": "SoC",
        "location": "EV",
        "unit": "Percent"
      },
      {
        "value": "70",
        "context": "Sample.Periodic",
        "format": "Raw",
        "measurand": "SoC",
        "location": "EV",
        "unit": "Percent"
      }
    ]
  }]
}]
```

**Message Components:**
- **Type**: `2` (CALL)
- **Message ID**: `"meter_001"` (unique identifier)
- **Action**: `"MeterValues"`
- **Payload**:
  - `connectorId`: Connector number (integer)
  - `transactionId`: Transaction ID from StartTransaction response (integer)
  - `meterValue`: Array of meter reading objects
    - `timestamp`: ISO 8601 timestamp of the reading (string)
    - `sampledValue`: Array of measured values
      - `value`: The measured value (string)
      - `context`: Context of the reading
        - `"Sample.Periodic"` - Periodic sample during transaction
        - `"Transaction.Begin"` - Value at transaction start
        - `"Transaction.End"` - Value at transaction end
      - `format`: Data format (`"Raw"` for numeric values)
      - `measurand`: Type of measurement
        - `"Energy.Active.Import.Register"` - Cumulative energy imported (Wh)
        - `"Power.Active.Import"` - Current power being imported (W)
        - `"Power.Offered"` - Maximum power offered (W)
        - `"Current.Import"` - Current being imported (A)
        - `"Voltage"` - Voltage (V)
        - `"Temperature"` - Temperature (°C)
        - `"SoC"` - State of Charge (%)
      - `location`: Measurement location
        - `"Outlet"` - At the charging outlet
        - `"EV"` - In the electric vehicle
        - `"Cable"` - In the charging cable
      - `unit`: Unit of measurement (Wh, W, A, V, Celsius, Percent)

### Phase 3.2: CMS → Charger (Meter Values Response)

The CMS acknowledges receipt of the meter values.

**Message Format:**
```json
[3, "meter_001", {}]
```

**Message Components:**
- **Type**: `3` (CALLRESULT)
- **Message ID**: `"meter_001"` (matches the request ID)
- **Payload**: Empty object `{}` (no additional data required)

**Note:** Meter values are typically sent periodically (e.g., every 30 seconds) throughout the charging session.

---

## 4. Remote Stop Transaction

### Phase 4.1: CMS → Charger (Remote Stop Request)

The CMS initiates a remote stop of the active transaction.

**Message Format:**
```json
[2, "a41e1146-fb85-4fb2-80a5-453882bd4645", "RemoteStopTransaction", {
  "transactionId": 9
}]
```

**Message Components:**
- **Type**: `2` (CALL)
- **Message ID**: `"a41e1146-fb85-4fb2-80a5-453882bd4645"` (unique identifier)
- **Action**: `"RemoteStopTransaction"`
- **Payload**:
  - `transactionId`: Transaction ID to stop (integer)

### Phase 4.2: Charger → CMS (Remote Stop Response)

The charger responds with the status of the remote stop request.

**Message Format:**
```json
[3, "remote_stop_001", {
  "status": "Accepted"
}]
```

**Message Components:**
- **Type**: `3` (CALLRESULT)
- **Message ID**: `"remote_stop_001"` (matches the original request ID)
- **Payload**:
  - `status`: Status of the remote stop request
    - `"Accepted"` - Request accepted, transaction will stop
    - `"Rejected"` - Request rejected (e.g., transaction not found or already stopped)

---

## 5. Stop Transaction

### Phase 5.1: Charger → CMS (Stop Transaction Request)

After accepting the remote stop, the charger sends a `StopTransaction` message to finalize the transaction.

**Message Format:**
```json
[2, "stop_001", "StopTransaction", {
  "transactionId": 9,
  "timestamp": "2025-11-29T10:45:48+02:00",
  "meterStop": 41500,
  "reason": "Local"
}]
```

**Message Components:**
- **Type**: `2` (CALL)
- **Message ID**: `"stop_001"` (unique identifier)
- **Action**: `"StopTransaction"`
- **Payload**:
  - `transactionId`: Transaction ID being stopped (integer)
  - `timestamp`: ISO 8601 timestamp when transaction stopped (string)
  - `meterStop`: Final meter reading in Wh (integer)
  - `reason`: Reason for stopping the transaction
    - `"Local"` - Stopped by user or locally
    - `"Remote"` - Stopped remotely by CMS
    - `"DeAuthorized"` - Stopped due to deauthorization
    - `"EmergencyStop"` - Emergency stop activated
    - `"EVDisconnected"` - EV disconnected
    - `"HardReset"` - Hard reset occurred
    - `"Other"` - Other reason

### Phase 5.2: CMS → Charger (Stop Transaction Response)

The CMS responds with the final authorization status.

**Message Format:**
```json
[3, "stop_001", {
  "idTagInfo": {
    "status": "Accepted"
  }
}]
```

**Message Components:**
- **Type**: `3` (CALLRESULT)
- **Message ID**: `"stop_001"` (matches the request ID)
- **Payload**:
  - `idTagInfo`: Final authorization information
    - `status`: Authorization status (same values as StartTransaction response)

---

## Complete Flow Sequence Diagram

```
CMS                          Charger
 |                              |
 |--[RemoteStartTransaction]-->|
 |                              |
 |<--[RemoteStartResponse]------|
 |                              |
 |                              |
 |<--[StartTransaction]---------|
 |                              |
 |--[StartTransactionResponse]->|
 |                              |
 |                              |
 |<--[MeterValues]--------------| (periodic)
 |                              |
 |--[MeterValuesResponse]------>|
 |                              |
 |                              |
 |<--[MeterValues]--------------| (periodic)
 |                              |
 |--[MeterValuesResponse]------>|
 |                              |
 |--[RemoteStopTransaction]---->|
 |                              |
 |<--[RemoteStopResponse]-------|
 |                              |
 |                              |
 |<--[StopTransaction]----------|
 |                              |
 |--[StopTransactionResponse]-->|
 |                              |
```

---

## Key Points

1. **Message IDs**: Each request must have a unique message ID. The response uses the same message ID to correlate with the request.

2. **Transaction ID**: Assigned by the CMS in the StartTransaction response and used throughout the transaction lifecycle.

3. **Meter Values Frequency**: Meter values are sent periodically during charging (typically every 30 seconds or as configured).

4. **Error Handling**: If any message fails or times out, the system should implement retry logic and error handling.

5. **Authorization**: The `idTagInfo.status` in StartTransaction and StopTransaction responses indicates whether the RFID tag is authorized.

6. **Meter Readings**: The difference between `meterStop` and `meterStart` (or cumulative energy from MeterValues) represents the total energy consumed during the transaction.

---

## Status Values Reference

### RemoteStartTransaction / RemoteStopTransaction Status
- `"Accepted"` - Request accepted
- `"Rejected"` - Request rejected

### idTagInfo Status
- `"Accepted"` - RFID tag is authorized
- `"Blocked"` - RFID tag is blocked
- `"Expired"` - RFID tag has expired
- `"Invalid"` - RFID tag is invalid
- `"ConcurrentTx"` - RFID tag already has an active transaction

### StopTransaction Reason
- `"Local"` - Stopped locally
- `"Remote"` - Stopped remotely
- `"DeAuthorized"` - Deauthorized
- `"EmergencyStop"` - Emergency stop
- `"EVDisconnected"` - EV disconnected
- `"HardReset"` - Hard reset
- `"Other"` - Other reason

---

## Testing

To test this flow:

1. Ensure the charger is connected to the CMS via WebSocket
2. Send RemoteStartTransaction from CMS
3. Verify StartTransaction is received from charger
4. Monitor MeterValues messages during charging
5. Send RemoteStopTransaction from CMS
6. Verify StopTransaction is received from charger

For detailed testing procedures, refer to:
- `OCPP_TEST_SUITE_README.md`
- `OCPP_POSTMAN_TESTING_GUIDE.md`

