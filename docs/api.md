# API Documentation

**Version:** 1.0.0  
**Last Updated:** 2025-11-22  
**Base URL:** `/api/v1/`

## Quick Links

- **Interactive API Documentation (Swagger UI):** `/api/docs/`
- **Alternative Documentation (ReDoc):** `/api/redoc/`
- **OpenAPI Schema (JSON):** `/api/schema/?format=json`
- **OpenAPI Schema (YAML):** `/api/schema/?format=yaml`
- **API Root:** `/api/v1/` - Lists all available endpoints

## Authentication

Currently using **Django session authentication**. Future: JWT tokens.

**Session Authentication:**
- Login via Django admin: `/admin/`
- Or use Django REST Framework browsable API
- Session cookie is automatically sent with requests

**Anonymous Access:**
- Some endpoints support anonymous access (e.g., viewing polls)
- Anonymous voting is supported with fingerprint validation
- Rate limits are stricter for anonymous users

## Base URLs

- **Development:** `http://localhost:8001/api/v1/` (Docker) or `http://localhost:8000/api/v1/` (local)
- **Production:** `https://yourdomain.com/api/v1/`

## Endpoints Overview

### Polls (`/api/v1/polls/`)

#### List Polls
```
GET /api/v1/polls/
```

**Query Parameters:**
- `search` - Search by title, description, or tag name
- `ordering` - Order by: `created_at`, `starts_at`, `ends_at`, `cached_total_votes` (prefix with `-` for descending)
- `is_active` - Filter by active status (true/false)
- `category` - Filter by category slug
- `tags` - Filter by comma-separated tag slugs
- `include_drafts` - Include draft polls (only visible to owner)

**Response:**
```json
{
  "count": 10,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Poll Title",
      "description": "Poll description",
      "created_by": {
        "id": 1,
        "username": "username"
      },
      "created_at": "2024-01-01T00:00:00Z",
      "starts_at": "2024-01-01T00:00:00Z",
      "ends_at": "2024-01-31T23:59:59Z",
      "is_active": true,
      "is_draft": false,
      "is_open": true,
      "category": {
        "id": 1,
        "name": "Politics",
        "slug": "politics"
      },
      "tags": [
        {"id": 1, "name": "election", "slug": "election"}
      ],
      "options": [
        {"id": 1, "text": "Option 1", "order": 0},
        {"id": 2, "text": "Option 2", "order": 1}
      ],
      "cached_total_votes": 100,
      "cached_unique_voters": 95
    }
  ]
}
```

#### Create Poll
```
POST /api/v1/polls/
```

**Request Body:**
```json
{
  "title": "New Poll",
  "description": "Poll description",
  "starts_at": "2024-01-01T00:00:00Z",
  "ends_at": "2024-01-31T23:59:59Z",
  "is_active": true,
  "is_draft": false,
  "category": 1,
  "tags": [1, 2],
  "options": [
    {"text": "Option 1", "order": 0},
    {"text": "Option 2", "order": 1}
  ],
  "settings": {
    "allow_multiple_votes": false,
    "show_results": true,
    "allow_vote_retraction": true
  },
  "security_rules": {
    "allowed_countries": ["KE"],
    "blocked_countries": [],
    "allowed_regions": [],
    "blocked_regions": []
  }
}
```

**Rate Limit:** 10 polls/hour

#### Get Poll Details
```
GET /api/v1/polls/{id}/
```

#### Update Poll
```
PATCH /api/v1/polls/{id}/
PUT /api/v1/polls/{id}/
```

**Note:** Only poll creator can update.

#### Delete Poll
```
DELETE /api/v1/polls/{id}/
```

**Note:** Only poll creator can delete.

#### Publish Draft Poll
```
POST /api/v1/polls/{id}/publish/
```

Publishes a draft poll, making it visible publicly.

#### Clone Poll
```
POST /api/v1/polls/{id}/clone/
```

**Request Body (optional):**
```json
{
  "title": "Cloned Poll Title",
  "is_draft": true
}
```

#### Add Options to Poll
```
POST /api/v1/polls/{id}/options/
```

**Request Body:**
```json
{
  "options": [
    {"text": "New Option 1", "order": 2},
    {"text": "New Option 2", "order": 3}
  ]
}
```

#### Remove Option from Poll
```
DELETE /api/v1/polls/{id}/options/{option_id}/
```

#### Get Poll Results
```
GET /api/v1/polls/{id}/results/
```

**Query Parameters:**
- `export_format` - Export format: `json` (default), `csv`, `pdf`

**Response:**
```json
{
  "poll_id": 1,
  "poll_title": "Poll Title",
  "total_votes": 100,
  "unique_voters": 95,
  "results": [
    {
      "option_id": 1,
      "option_text": "Option 1",
      "votes": 60,
      "percentage": 60.0
    },
    {
      "option_id": 2,
      "option_text": "Option 2",
      "votes": 40,
      "percentage": 40.0
    }
  ]
}
```

#### Get Live Results (WebSocket-ready)
```
GET /api/v1/polls/{id}/results/live/
```

Returns real-time poll results suitable for WebSocket updates.

#### Export Vote Log
```
GET /api/v1/polls/{id}/export-vote-log/
```

**Query Parameters:**
- `export_format` - `json` (default), `csv`, `pdf`

#### Export Analytics Report
```
GET /api/v1/polls/{id}/export-analytics/
```

**Query Parameters:**
- `export_format` - `json` (default), `csv`, `pdf`

#### Export Audit Trail
```
GET /api/v1/polls/{id}/export-audit-trail/
```

**Query Parameters:**
- `export_format` - `json` (default), `csv`, `pdf`
- `start_date` - ISO format date (e.g., `2024-01-01T00:00:00Z`)
- `end_date` - ISO format date

#### Get Poll Analytics
```
GET /api/v1/polls/{id}/analytics/
```

Returns comprehensive analytics including:
- Total votes over time
- Voter demographics
- Participation rate
- Geographic distribution

#### Get Poll Templates
```
GET /api/v1/polls/templates/
```

Lists available poll templates.

#### Get Template Details
```
GET /api/v1/polls/templates/{template_id}/
```

#### Create Poll from Template
```
POST /api/v1/polls/from-template/
```

**Request Body:**
```json
{
  "template_id": "election",
  "title": "My Poll Title",
  "customizations": {}
}
```

### Votes (`/api/v1/votes/`)

#### Cast a Vote
```
POST /api/v1/votes/cast/
```

**Request Body:**
```json
{
  "poll_id": 1,
  "choice_id": 2,
  "idempotency_key": "unique-key-123"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "user": {
    "id": 1,
    "username": "username"
  },
  "option": {
    "id": 2,
    "text": "Option 2"
  },
  "poll": {
    "id": 1,
    "title": "Poll Title"
  },
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Response (200 OK - Idempotent Retry):**
If the same `idempotency_key` is used, returns existing vote with 200 status.

**Error Responses:**
- `400`: Invalid vote, poll closed, CAPTCHA failure, or geographic restriction
- `401`: Authentication required (if poll requires authentication)
- `403`: Fraud detected or IP blocked
- `404`: Poll or option not found
- `409`: Duplicate vote (user already voted)
- `429`: Rate limit exceeded

**Rate Limits:**
- Anonymous users: 50 votes/hour
- Authenticated users: 200 votes/hour

#### Get My Votes
```
GET /api/v1/votes/my-votes/
```

Returns all votes cast by the authenticated user.

#### Retract Vote
```
DELETE /api/v1/votes/{id}/
```

Retracts (deletes) a vote. Only allowed if:
- User owns the vote
- Poll allows vote retraction (`poll.settings.allow_vote_retraction = true`)
- Poll is still open

### Categories (`/api/v1/categories/`)

#### List Categories
```
GET /api/v1/categories/
```

#### Get Category Details
```
GET /api/v1/categories/{id}/
```

#### Create Category
```
POST /api/v1/categories/
```

**Request Body:**
```json
{
  "name": "Politics",
  "description": "Political polls"
}
```

### Tags (`/api/v1/tags/`)

#### List Tags
```
GET /api/v1/tags/
```

#### Get Tag Details
```
GET /api/v1/tags/{id}/
```

#### Create Tag
```
POST /api/v1/tags/
```

**Request Body:**
```json
{
  "name": "election"
}
```

### Users (`/api/v1/users/`)

#### List Users
```
GET /api/v1/users/
```

#### Get User Details
```
GET /api/v1/users/{id}/
```

#### Follow User
```
POST /api/v1/users/{id}/follow/
```

#### Unfollow User
```
DELETE /api/v1/users/{id}/follow/
```

#### Get User's Polls
```
GET /api/v1/users/{id}/polls/
```

### Analytics (`/api/v1/analytics/`)

#### List Analytics
```
GET /api/v1/analytics/
```

#### Get Poll Analytics
```
GET /api/v1/analytics/{id}/
```

### Notifications (`/api/v1/notifications/`)

#### List Notifications
```
GET /api/v1/notifications/
```

#### Mark Notification as Read
```
PATCH /api/v1/notifications/{id}/
```

#### Mark All as Read
```
POST /api/v1/notifications/mark-all-read/
```

#### Get Unread Count
```
GET /api/v1/notifications/unread-count/
```

#### Unsubscribe
```
POST /api/v1/notifications/unsubscribe/
```

## Idempotency

Vote creation supports **idempotency keys** to prevent duplicate votes from network retries or client errors.

### How It Works

1. **Generate a unique idempotency key** (e.g., UUID, timestamp-based hash)
2. **Include it in the vote request:**
   ```json
   {
     "poll_id": 1,
     "choice_id": 2,
     "idempotency_key": "550e8400-e29b-41d4-a716-446655440000"
   }
   ```
3. **First request:** Creates vote, returns `201 Created`
4. **Subsequent requests with same key:** Returns existing vote with `200 OK`

### Best Practices

- **Generate keys client-side** (don't rely on server
- **Use UUIDs** or SHA256 hashes of request content
- **Store keys** to retry failed requests safely
- **Key format:** 64 characters or less (alphanumeric, hyphens, underscores)

**Code Reference:** `backend/apps/votes/services.py` - `cast_vote` function

## Rate Limiting

### Rate Limit Tiers

| User Type | General API | Voting | Poll Creation | Poll Reading |
|-----------|-------------|--------|---------------|--------------|
| Anonymous | 100/hour | 50/hour | 10/hour | 200/hour |
| Authenticated | 1000/hour | 200/hour | 10/hour | 200/hour |
| Per IP | 100/minute | - | - | - |

### Rate Limit Headers

All responses include rate limit headers:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1704067200
```

### Rate Limit Exceeded Response

```json
{
  "error": "Rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

**Status Code:** `429 Too Many Requests`

**Code Reference:** `backend/core/middleware/rate_limit.py`, `backend/core/throttles.py`

## Geographic Restrictions

Polls can be configured to restrict voting based on the voter's IP address country or region.

### Configuration

Set `security_rules` when creating/updating a poll:

```json
{
  "security_rules": {
    "allowed_countries": ["KE"],
    "blocked_countries": [],
    "allowed_regions": [],
    "blocked_regions": []
  }
}
```

### Country Codes

Use ISO 3166-1 alpha-2 country codes (e.g., `KE` for Kenya, `US` for United States).

### Error Response

If voting is blocked due to geographic restrictions:

```json
{
  "error": "Voting is not allowed from your location",
  "error_code": "GeographicRestrictionError"
}
```

**Status Code:** `400 Bad Request`

**Code Reference:** `backend/core/utils/geolocation.py`, `backend/apps/votes/services.py`

## Fraud Detection

The system employs various fraud detection mechanisms:

- **Fingerprint Analysis:** Browser/device fingerprinting
- **IP Reputation:** IP address analysis
- **Vote Patterns:** Unusual voting patterns
- **Rate Limiting:** Prevents brute-force attacks

### Fraud Detection Response

If fraud is detected:

```json
{
  "error": "Fraud detected. Vote rejected.",
  "error_code": "FraudDetectedError"
}
```

**Status Code:** `403 Forbidden`

## Error Responses

All errors follow this format:

```json
{
  "error": "Error message",
  "error_code": "ErrorCode"  // Optional
}
```

### Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| `200` | Success | - |
| `201` | Created | New resource created |
| `400` | Bad Request | Invalid input, poll closed, geographic restriction |
| `401` | Unauthorized | Authentication required |
| `403` | Forbidden | Fraud detected, IP blocked, insufficient permissions |
| `404` | Not Found | Resource doesn't exist |
| `409` | Conflict | Duplicate vote, resource conflict |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Server Error | Internal server error |

## Pagination

List endpoints support pagination:

**Query Parameters:**
- `page` - Page number (default: 1)
- `page_size` - Items per page (default: 20, max: 100)

**Response Format:**
```json
{
  "count": 100,
  "next": "http://api.example.com/api/v1/polls/?page=2",
  "previous": null,
  "results": [...]
}
```

## Filtering and Search

### Search

Use `search` parameter to search across multiple fields:
```
GET /api/v1/polls/?search=election
```

### Ordering

Use `ordering` parameter to sort results:
```
GET /api/v1/polls/?ordering=-created_at
GET /api/v1/polls/?ordering=starts_at,-cached_total_votes
```

Prefix with `-` for descending order.

### Filtering

Filter by specific fields:
```
GET /api/v1/polls/?is_active=true&category=politics&tags=election,presidential
```

## Export Formats

Export endpoints support multiple formats:

- **JSON** (default): `?export_format=json`
- **CSV**: `?export_format=csv`
- **PDF**: `?export_format=pdf`

**Example:**
```
GET /api/v1/polls/1/results/?export_format=csv
```

## Interactive API Documentation

### Swagger UI
Visit `/api/docs/` for interactive API exploration with:
- Try-it-out functionality
- Request/response examples
- Authentication testing
- Schema browsing

### ReDoc
Visit `/api/redoc/` for alternative documentation format with:
- Clean, readable layout
- Detailed descriptions
- Code examples

### OpenAPI Schema
Download the OpenAPI 3.0 schema:
- JSON: `/api/schema/?format=json`
- YAML: `/api/schema/?format=yaml`

Use these schemas for:
- API client code generation
- Import into Postman/Insomnia
- CI/CD integration
- API testing tools

## Best Practices

1. **Always use HTTPS** in production
2. **Include idempotency keys** for vote requests
3. **Handle rate limits** gracefully (check headers, implement backoff)
4. **Use pagination** for large datasets
5. **Cache responses** when appropriate
6. **Monitor rate limit headers** to avoid hitting limits
7. **Handle errors** appropriately based on status codes
8. **Use appropriate HTTP methods** (GET for reads, POST for creates, etc.)

## Support

- **API Documentation:** `/api/docs/` or `/api/redoc/`
- **Schema Viewer:** `/api/schema/view/`
- **Architecture Docs:** `docs/architecture-comprehensive.md`
- **Deployment Guide:** `docs/deployment-guide.md`

---

**Last Updated:** 2025-11-22  
**API Version:** 1.0.0
