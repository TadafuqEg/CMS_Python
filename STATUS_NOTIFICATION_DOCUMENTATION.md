# OCPP 1.6 StatusNotification Documentation

This document provides comprehensive documentation for the `StatusNotification` message in OCPP 1.6, including all possible status values, error codes, and when they occur.

## Overview

The `StatusNotification` message is sent by the Charge Point (Charger) to the Central Management System (CMS) to report the current status of a connector or the entire charging point. This message is crucial for real-time monitoring and management of charging infrastructure.

**Message Type**: CALL (Type 2)  
**Direction**: Charger → CMS  
**Frequency**: Sent whenever the connector status changes

---

## Message Format

### Request (Charger → CMS)

```json
[2, "message_id", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Available",
  "info": "Optional additional information",
  "timestamp": "2025-11-29T10:12:48+02:00"
}]
```

### Response (CMS → Charger)

```json
[3, "message_id", {}]
```

**Note**: The response is always an empty object `{}` - no additional data is required.

---

## Message Fields

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `connectorId` | Integer | The identifier of the connector. **0** indicates the status applies to the entire charging point (all connectors). |
| `status` | String | The current status of the connector (see Status Values below). |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `errorCode` | String | Error code if applicable (see Error Codes below). Default: `"NoError"` |
| `info` | String | Additional information about the status (optional). |
| `timestamp` | String | ISO 8601 timestamp when the status change occurred (optional). |

---

## Connector ID

The `connectorId` field has special meaning:

- **connectorId = 0**: Status applies to the **entire charging point** (all connectors). Used for:
  - Charging point-level faults
  - Power loss affecting all connectors
  - Maintenance mode for the entire station
  - Network connectivity issues

- **connectorId ≥ 1**: Status applies to a **specific connector**:
  - Connector 1, 2, 3, etc.
  - Each connector reports its own status independently

---

## Status Values

The `status` field indicates the current operational state of the connector. Below are all possible status values and when they occur:

### 1. Available

**Status**: `"Available"`

**When it occurs**:
- Connector is ready for use
- No vehicle is connected
- No active charging session
- Connector is operational and waiting for a user
- After a charging session ends and the cable is unplugged
- After maintenance is completed
- After a fault is cleared

**Typical flow**: `Faulted` → `Available` (after fault cleared)

**Example**:
```json
[2, "status_001", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Available"
}]
```

---

### 2. Preparing

**Status**: `"Preparing"`

**When it occurs**:
- User has plugged in the charging cable
- Vehicle is detected but charging hasn't started yet
- Authorization is in progress (waiting for RFID scan)
- Connector is initializing the charging session
- Handshake between EV and charger is in progress
- Pre-charge safety checks are being performed

**Typical flow**: `Available` → `Preparing` → `Charging`

**Example**:
```json
[2, "status_002", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Preparing"
}]
```

---

### 3. Charging

**Status**: `"Charging"`

**When it occurs**:
- Active charging session is in progress
- Energy is being delivered to the vehicle
- Transaction is active (StartTransaction has been sent)
- Connector is actively charging the EV battery
- Meter values are being reported periodically

**Typical flow**: `Preparing` → `Charging` → `Finishing`

**Example**:
```json
[2, "status_003", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Charging"
}]
```

---

### 4. SuspendedEV

**Status**: `"SuspendedEV"`

**When it occurs**:
- Charging is temporarily suspended by the **Electric Vehicle (EV)**
- EV has requested a pause in charging (e.g., battery management system)
- EV is regulating its own charging rate
- Vehicle is in a cooling/heating cycle
- EV has reached a temperature limit and paused charging
- User paused charging from the vehicle's interface

**Typical flow**: `Charging` → `SuspendedEV` → `Charging` (resume)

**Note**: The transaction remains active, but energy delivery is paused.

**Example**:
```json
[2, "status_004", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "SuspendedEV"
}]
```

---

### 5. SuspendedEVSE

**Status**: `"SuspendedEVSE"`

**When it occurs**:
- Charging is temporarily suspended by the **Charging Station (EVSE)**
- Load management system has reduced/stopped power
- Grid constraints require power reduction
- Smart charging algorithms are managing power distribution
- Remote command to suspend charging
- Power limit reached and station is managing load
- Scheduled charging pause

**Typical flow**: `Charging` → `SuspendedEVSE` → `Charging` (resume)

**Note**: The transaction remains active, but energy delivery is paused by the station.

**Example**:
```json
[2, "status_005", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "SuspendedEVSE"
}]
```

---

### 6. Finishing

**Status**: `"Finishing"`

**When it occurs**:
- Charging session has ended (StopTransaction sent or received)
- Energy delivery has stopped
- Vehicle is still connected (cable not unplugged yet)
- Waiting for user to unplug the cable
- Final meter readings are being processed
- Transaction is being finalized

**Typical flow**: `Charging` → `Finishing` → `Available` (after unplug)

**Example**:
```json
[2, "status_006", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Finishing"
}]
```

---

### 7. Reserved

**Status**: `"Reserved"`

**When it occurs**:
- Connector has been reserved for a specific user
- Reservation was created via `ReserveNow` command
- Connector is reserved but not yet in use
- User has a scheduled reservation
- Connector is locked for a specific RFID card

**Typical flow**: `Available` → `Reserved` → `Preparing` → `Charging`

**Note**: The connector cannot be used by other users until the reservation expires or is cancelled.

**Example**:
```json
[2, "status_007", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Reserved"
}]
```

---

### 8. Unavailable

**Status**: `"Unavailable"`

**When it occurs**:
- Connector is out of service
- Maintenance mode is active
- Connector is disabled by operator
- Manual lockout by maintenance staff
- Connector is intentionally taken offline
- Software update in progress
- Configuration changes being applied
- Connector is not operational but not faulted

**Typical flow**: `Available` → `Unavailable` → `Available` (after maintenance)

**Note**: This is different from `Faulted` - `Unavailable` is intentional, while `Faulted` indicates an error condition.

**Example**:
```json
[2, "status_008", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Unavailable"
}]
```

---

### 9. Faulted

**Status**: `"Faulted"`

**When it occurs**:
- An error condition has been detected
- Hardware malfunction
- Communication failure with vehicle
- Safety system triggered
- Power delivery failure
- Connector lock mechanism failure
- Ground fault detected
- Overcurrent/overvoltage condition
- Temperature sensor failure
- Any critical error that prevents operation

**Typical flow**: `Charging` → `Faulted` → `Available` (after fault cleared)

**Note**: When `Faulted` status is reported, an `errorCode` should also be included to indicate the specific fault.

**Example**:
```json
[2, "status_009", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "GroundFailure",
  "status": "Faulted"
}]
```

---

## Error Codes

The `errorCode` field provides additional information about the connector's condition. Error codes can be reported with any status, but are most commonly associated with `Faulted` status.

### 1. NoError

**Error Code**: `"NoError"`

**When it occurs**:
- No error condition exists
- Connector is operating normally
- Default value when no error is present
- Error condition has been cleared

**Example**:
```json
[2, "status_001", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Available"
}]
```

---

### 2. ConnectorLockFailure

**Error Code**: `"ConnectorLockFailure"`

**When it occurs**:
- Connector lock mechanism failed to engage
- Connector lock failed to disengage
- Lock actuator malfunction
- Mechanical failure in locking system
- Lock sensor indicates failure

**Associated Status**: Usually `"Faulted"`

**Example**:
```json
[2, "status_010", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "ConnectorLockFailure",
  "status": "Faulted"
}]
```

---

### 3. EVCommunicationError

**Error Code**: `"EVCommunicationError"`

**When it occurs**:
- Communication with Electric Vehicle failed
- CAN bus communication error
- PLC (Power Line Communication) failure
- Vehicle handshake failed
- Protocol mismatch with vehicle
- Vehicle disconnected unexpectedly during charging

**Associated Status**: Usually `"Faulted"` or `"Unavailable"`

**Example**:
```json
[2, "status_011", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "EVCommunicationError",
  "status": "Faulted"
}]
```

---

### 4. GroundFailure

**Error Code**: `"GroundFailure"`

**When it occurs**:
- Ground fault detected
- Insulation failure
- Safety system triggered ground fault protection
- Electrical safety issue detected
- GFCI (Ground Fault Circuit Interrupter) tripped

**Associated Status**: Always `"Faulted"` (critical safety issue)

**Example**:
```json
[2, "status_012", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "GroundFailure",
  "status": "Faulted"
}]
```

---

### 5. HighTemperature

**Error Code**: `"HighTemperature"`

**When it occurs**:
- Charging cable temperature too high
- Connector overheating
- Ambient temperature exceeds limits
- Thermal protection activated
- Cooling system failure
- Temperature sensor reading above threshold

**Associated Status**: Usually `"Faulted"` or `"SuspendedEVSE"`

**Example**:
```json
[2, "status_013", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "HighTemperature",
  "status": "Faulted"
}]
```

---

### 6. InternalError

**Error Code**: `"InternalError"`

**When it occurs**:
- Internal software error
- Firmware crash or exception
- Memory error
- Unexpected internal state
- System malfunction
- Generic internal failure

**Associated Status**: Usually `"Faulted"` or `"Unavailable"`

**Example**:
```json
[2, "status_014", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "InternalError",
  "status": "Faulted"
}]
```

---

### 7. LocalListConflict

**Error Code**: `"LocalListConflict"`

**When it occurs**:
- Conflict in local authorization list
- Duplicate entries in local list
- Version mismatch in local list
- Corrupted local authorization data
- List update conflict

**Associated Status**: Usually `"Unavailable"` or `"Faulted"`

**Example**:
```json
[2, "status_015", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "LocalListConflict",
  "status": "Unavailable"
}]
```

---

### 8. OtherError

**Error Code**: `"OtherError"`

**When it occurs**:
- Error that doesn't fit other categories
- Unknown error condition
- Generic error placeholder
- Custom error not in standard list

**Associated Status**: Usually `"Faulted"`

**Example**:
```json
[2, "status_016", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "OtherError",
  "status": "Faulted",
  "info": "Custom error description"
}]
```

---

### 9. OverCurrentFailure

**Error Code**: `"OverCurrentFailure"`

**When it occurs**:
- Current exceeds maximum allowed
- Overcurrent protection triggered
- Current sensor reading above threshold
- Circuit breaker tripped due to overcurrent
- Power delivery exceeds rated capacity

**Associated Status**: Always `"Faulted"` (safety issue)

**Example**:
```json
[2, "status_017", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "OverCurrentFailure",
  "status": "Faulted"
}]
```

---

### 10. PowerMeterFailure

**Error Code**: `"PowerMeterFailure"`

**When it occurs**:
- Power meter hardware failure
- Meter readings are invalid or missing
- Meter communication failure
- Meter calibration error
- Meter sensor malfunction

**Associated Status**: Usually `"Faulted"` or `"Unavailable"`

**Example**:
```json
[2, "status_018", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "PowerMeterFailure",
  "status": "Faulted"
}]
```

---

### 11. PowerSwitchFailure

**Error Code**: `"PowerSwitchFailure"`

**When it occurs**:
- Power switch/relay failure
- Contactor failed to engage
- Contactor failed to disengage
- Power switching mechanism malfunction
- Relay stuck in open or closed position

**Associated Status**: Always `"Faulted"`

**Example**:
```json
[2, "status_019", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "PowerSwitchFailure",
  "status": "Faulted"
}]
```

---

### 12. ReaderFailure

**Error Code**: `"ReaderFailure"`

**When it occurs**:
- RFID reader hardware failure
- Reader communication error
- Reader sensor malfunction
- Card reading mechanism failed
- Reader not responding

**Associated Status**: Usually `"Unavailable"` or `"Faulted"`

**Example**:
```json
[2, "status_020", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "ReaderFailure",
  "status": "Unavailable"
}]
```

---

### 13. ResetFailure

**Error Code**: `"ResetFailure"`

**When it occurs**:
- Reset command failed to execute
- System reset incomplete
- Reset timeout
- Partial reset leaving system in inconsistent state
- Reset procedure error

**Associated Status**: Usually `"Faulted"` or `"Unavailable"`

**Example**:
```json
[2, "status_021", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "ResetFailure",
  "status": "Faulted"
}]
```

---

### 14. UnderVoltage

**Error Code**: `"UnderVoltage"`

**When it occurs**:
- Supply voltage below minimum threshold
- Low voltage condition detected
- Power supply voltage drop
- Grid voltage too low
- Voltage sensor reading below minimum

**Associated Status**: Usually `"Faulted"` or `"SuspendedEVSE"`

**Example**:
```json
[2, "status_022", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "UnderVoltage",
  "status": "Faulted"
}]
```

---

### 15. OverVoltage

**Error Code**: `"OverVoltage"`

**When it occurs**:
- Supply voltage above maximum threshold
- High voltage condition detected
- Power supply voltage surge
- Grid voltage too high
- Voltage sensor reading above maximum

**Associated Status**: Always `"Faulted"` (safety issue)

**Example**:
```json
[2, "status_023", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "OverVoltage",
  "status": "Faulted"
}]
```

---

### 16. WeakSignal

**Error Code**: `"WeakSignal"`

**When it occurs**:
- Weak communication signal
- Network connectivity issues
- WiFi/cellular signal too weak
- Communication link degraded
- Signal strength below threshold

**Associated Status**: Usually `"Unavailable"` or `"Faulted"`

**Example**:
```json
[2, "status_024", "StatusNotification", {
  "connectorId": 0,
  "errorCode": "WeakSignal",
  "status": "Unavailable"
}]
```

**Note**: WeakSignal often affects the entire charging point (connectorId = 0).

---

## Status Transition Flow

### Normal Charging Flow

```
Available → Preparing → Charging → Finishing → Available
```

### Charging with Suspension

```
Charging → SuspendedEV → Charging (resume)
Charging → SuspendedEVSE → Charging (resume)
```

### Reservation Flow

```
Available → Reserved → Preparing → Charging → Finishing → Available
```

### Fault Flow

```
Charging → Faulted (with errorCode) → Available (after fault cleared)
Available → Faulted (with errorCode) → Available (after fault cleared)
```

### Maintenance Flow

```
Available → Unavailable → Available (after maintenance)
```

---

## Complete StatusNotification Examples

### Example 1: Connector Available

```json
[2, "status_001", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Available",
  "timestamp": "2025-11-29T10:00:00+02:00"
}]
```

### Example 2: Charging Started

```json
[2, "status_002", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Charging",
  "timestamp": "2025-11-29T10:12:48+02:00"
}]
```

### Example 3: Ground Fault Detected

```json
[2, "status_003", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "GroundFailure",
  "status": "Faulted",
  "info": "Ground fault detected on connector 1",
  "timestamp": "2025-11-29T10:30:15+02:00"
}]
```

### Example 4: Charging Suspended by EV

```json
[2, "status_004", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "SuspendedEV",
  "timestamp": "2025-11-29T10:45:00+02:00"
}]
```

### Example 5: Whole Charging Point Unavailable

```json
[2, "status_005", "StatusNotification", {
  "connectorId": 0,
  "errorCode": "WeakSignal",
  "status": "Unavailable",
  "info": "Network connectivity lost",
  "timestamp": "2025-11-29T11:00:00+02:00"
}]
```

### Example 6: High Temperature Fault

```json
[2, "status_006", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "HighTemperature",
  "status": "Faulted",
  "info": "Cable temperature: 85°C",
  "timestamp": "2025-11-29T11:15:30+02:00"
}]
```

### Example 7: Connector Reserved

```json
[2, "status_007", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Reserved",
  "timestamp": "2025-11-29T11:30:00+02:00"
}]
```

### Example 8: Charging Finished

```json
[2, "status_008", "StatusNotification", {
  "connectorId": 1,
  "errorCode": "NoError",
  "status": "Finishing",
  "timestamp": "2025-11-29T11:45:48+02:00"
}]
```

---

## Response Format

The CMS must respond to every StatusNotification with a CALLRESULT message:

```json
[3, "message_id", {}]
```

The response is always an empty object - no additional data is required or expected.

---

## Best Practices

1. **Always send StatusNotification on status changes**: The charger should send a StatusNotification whenever the connector status changes, not just periodically.

2. **Include errorCode**: Even when status is not `Faulted`, include `errorCode: "NoError"` for clarity.

3. **Use connectorId 0 appropriately**: Only use `connectorId: 0` for charging point-level issues that affect all connectors.

4. **Include timestamp**: While optional, including a timestamp helps with debugging and audit trails.

5. **Provide info field for faults**: When reporting faults, use the `info` field to provide additional context.

6. **Handle responses**: The charger should wait for the response before considering the status update acknowledged.

7. **Error recovery**: When a fault is cleared, send a new StatusNotification with `status: "Available"` and `errorCode: "NoError"`.

---

## Status Mapping to Simplified States

For UI/display purposes, OCPP statuses can be mapped to simplified states:

| OCPP Status | Simplified State | Description |
|-------------|------------------|-------------|
| `Available` | `available` | Ready for use |
| `Preparing` | `in_use` | In use (preparing) |
| `Charging` | `in_use` | In use (charging) |
| `SuspendedEV` | `in_use` | In use (suspended) |
| `SuspendedEVSE` | `in_use` | In use (suspended) |
| `Finishing` | `in_use` | In use (finishing) |
| `Reserved` | `in_use` | Reserved/in use |
| `Unavailable` | `unavailable` | Not available |
| `Faulted` | `unavailable` | Not available (fault) |

**Note**: If `errorCode` is present and not `"NoError"`, the connector should typically be considered `unavailable` regardless of status.

---

## Testing

To test StatusNotification messages:

1. **Test normal flow**: Send status changes in sequence: Available → Preparing → Charging → Finishing → Available

2. **Test fault conditions**: Send Faulted status with various error codes

3. **Test whole CP status**: Send StatusNotification with `connectorId: 0`

4. **Test error recovery**: Send Faulted status, then Available status

5. **Test suspension**: Send Charging → SuspendedEV → Charging

For testing examples, refer to:
- `test_status_notification.py`
- `OCPP_POSTMAN_TESTING_GUIDE.md`

---

## References

- OCPP 1.6 Specification
- `CHARGING_FLOW_DOCUMENTATION.md` - Complete charging flow
- `OCPP_POSTMAN_TESTING_GUIDE.md` - Testing procedures
- `SINGLE_SOCKET_IMPLEMENTATION.md` - Implementation details

