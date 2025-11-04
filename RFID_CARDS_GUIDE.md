# RFID Card Management Guide

## Overview

The RFID card authorization system checks RFID cards in the database when a charger sends an Authorize request. If the card exists and is valid, the authorization is accepted; otherwise, it's rejected.

## Database Table

The `rfid_cards` table stores RFID card information with the following fields:

- `id_tag` (String, unique) - RFID tag ID (primary identifier)
- `card_number` (String, optional) - Physical card number
- `holder_name` (String, optional) - Card holder name
- `description` (String, optional) - Optional description
- `is_active` (Boolean) - Whether card is active (default: True)
- `is_blocked` (Boolean) - Whether card is blocked (default: False)
- `expires_at` (DateTime, optional) - Card expiration date
- `user_id` (Integer, optional) - Associated user ID
- `organization_id` (String, optional) - Organization ID
- `site_id` (String, optional) - Site ID
- `metadata` (JSON) - Additional metadata
- `created_at`, `updated_at`, `last_used_at` - Timestamps

## Authorization Logic

When a charger sends an Authorize request:

1. **No idTag** → Returns `Invalid`
2. **Card not found** → Returns `Invalid`
3. **Card is blocked** → Returns `Blocked`
4. **Card is inactive** → Returns `Invalid`
5. **Card is expired** → Returns `Expired`
6. **Card is valid** → Returns `Accepted` and updates `last_used_at`

## Setup

### 1. Create Database Table

Run the migration script:

```bash
python migrate_add_rfid_cards.py
```

Or with test data:

```bash
python migrate_add_rfid_cards.py --test-data
```

### 2. Test Authorization

The test cards created:
- `TEST001` - Will be accepted
- `TEST002` - Will be accepted
- `TEST003` - Will be rejected (blocked)
- `EXPIRED001` - Will be rejected (expired)

## API Endpoints

### Create RFID Card

```bash
POST /api/rfid-cards
Content-Type: application/json

{
  "id_tag": "RFID123",
  "card_number": "CARD123",
  "holder_name": "John Doe",
  "is_active": true,
  "is_blocked": false
}
```

### List RFID Cards

```bash
GET /api/rfid-cards
GET /api/rfid-cards?is_active=true
GET /api/rfid-cards?is_blocked=false
GET /api/rfid-cards?organization_id=ORG001
```

### Get RFID Card

```bash
GET /api/rfid-cards/{id_tag}
```

### Update RFID Card

```bash
PUT /api/rfid-cards/{id_tag}
Content-Type: application/json

{
  "is_blocked": true,
  "holder_name": "Updated Name"
}
```

### Delete RFID Card

```bash
DELETE /api/rfid-cards/{id_tag}
```

### Block/Unblock Card

```bash
POST /api/rfid-cards/{id_tag}/block
POST /api/rfid-cards/{id_tag}/unblock
```

### Activate/Deactivate Card

```bash
POST /api/rfid-cards/{id_tag}/activate
POST /api/rfid-cards/{id_tag}/deactivate
```

### Check Card Status

```bash
GET /api/rfid-cards/{id_tag}/status
```

Returns:
```json
{
  "id_tag": "RFID123",
  "exists": true,
  "status": "Accepted",
  "is_active": true,
  "is_blocked": false,
  "expires_at": null,
  "last_used_at": "2025-01-29T12:00:00Z"
}
```

### Bulk Create Cards

```bash
POST /api/rfid-cards/bulk
Content-Type: application/json

[
  {
    "id_tag": "RFID001",
    "holder_name": "User 1"
  },
  {
    "id_tag": "RFID002",
    "holder_name": "User 2"
  }
]
```

## Testing Authorization

### Test with Valid Card

1. Create a card:
```bash
curl -X POST http://localhost:8001/api/rfid-cards \
  -H "Content-Type: application/json" \
  -d '{"id_tag": "RFID123", "holder_name": "Test User"}'
```

2. Send Authorize request from charger with `idTag: "RFID123"`
3. Expected response: `Accepted`

### Test with Invalid Card

1. Send Authorize request from charger with `idTag: "INVALID123"`
2. Expected response: `Invalid`

### Test with Blocked Card

1. Block a card:
```bash
curl -X POST http://localhost:8001/api/rfid-cards/RFID123/block
```

2. Send Authorize request with that card
3. Expected response: `Blocked`

## Example: Complete Flow

```python
# 1. Create RFID card
POST /api/rfid-cards
{
  "id_tag": "USER123",
  "holder_name": "John Doe",
  "is_active": true
}

# 2. Charger sends Authorize request
# OCPP Message: [2, "msg-id", "Authorize", {"idTag": "USER123"}]

# 3. CMS checks database
# - Card exists: ✅
# - Card is active: ✅
# - Card is not blocked: ✅
# - Card is not expired: ✅

# 4. CMS responds
# Response: [3, "msg-id", {"idTagInfo": {"status": "Accepted"}}]

# 5. Card's last_used_at is updated automatically
```

## Authorization Status Values

- `Accepted` - Card is valid and authorized
- `Blocked` - Card is blocked
- `Expired` - Card has expired
- `Invalid` - Card doesn't exist, is inactive, or invalid

## Best Practices

1. **Always set expiration dates** for time-limited access
2. **Use organization_id and site_id** for multi-tenant scenarios
3. **Block cards immediately** when lost or stolen
4. **Monitor last_used_at** for security auditing
5. **Use metadata** for additional card information

## Integration with Laravel

If you want to sync RFID cards from Laravel:

```php
// In Laravel - Create RFID card
$rfidCard = RfidCard::create([
    'id_tag' => $user->rfid_tag,
    'holder_name' => $user->name,
    'user_id' => $user->id,
    'is_active' => true,
]);

// Call Python CMS API to sync
Http::post('http://python-cms:8001/api/rfid-cards', [
    'id_tag' => $user->rfid_tag,
    'holder_name' => $user->name,
    'user_id' => $user->id,
    'is_active' => true,
]);
```

---

*Last Updated: 2025-01-29*

