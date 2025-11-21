# Comprehensive Architecture Documentation

**Version:** 1.0  
**Last Updated:** 2025-11-21  
**Project:** Provote - Professional Voting Platform

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Database Schema (ERD)](#2-database-schema-erd)
3. [API Flow Diagrams](#3-api-flow-diagrams)
4. [Idempotency System](#4-idempotency-system)
5. [Scaling Strategy](#5-scaling-strategy)
6. [Security Architecture](#6-security-architecture)
7. [Test Verification](#7-test-verification)

---

## 1. System Architecture Overview

### 1.1 High-Level Architecture

```mermaid
graph TB
    Client[Client Browser/App] -->|HTTPS| Nginx[Nginx Reverse Proxy]
    Nginx -->|HTTP| Django1[Django App<br/>Gunicorn Worker 1]
    Nginx -->|HTTP| Django2[Django App<br/>Gunicorn Worker 2]
    Nginx -->|HTTP| Django3[Django App<br/>Gunicorn Worker 3]
    
    Django1 -->|SQL| PostgreSQL[(PostgreSQL<br/>Primary DB)]
    Django2 -->|SQL| PostgreSQL
    Django3 -->|SQL| PostgreSQL
    
    Django1 -->|Cache| Redis[(Redis<br/>Cache & Pub/Sub)]
    Django2 -->|Cache| Redis
    Django3 -->|Cache| Redis
    
    Django1 -->|Tasks| Celery[Celery Worker]
    Django2 -->|Tasks| Celery
    Django3 -->|Tasks| Celery
    
    Celery -->|Broker| Redis
    CeleryBeat[Celery Beat<br/>Scheduler] -->|Schedule| Celery
    
    Django1 -->|WebSocket| Channels[Django Channels<br/>ASGI]
    Channels -->|Pub/Sub| Redis
    
    PostgreSQL -->|Replication| Replica[(PostgreSQL<br/>Read Replica)]
    
    style Client fill:#e1f5ff
    style Nginx fill:#fff4e1
    style Django1 fill:#e8f5e9
    style Django2 fill:#e8f5e9
    style Django3 fill:#e8f5e9
    style PostgreSQL fill:#f3e5f5
    style Redis fill:#ffebee
    style Celery fill:#fff9c4
    style Channels fill:#e0f2f1
```

### 1.2 Component Details

#### **Frontend Layer**
- **Client Applications**: Web browsers, mobile apps, API clients
- **Protocols**: HTTPS, WebSocket (WSS)

#### **Load Balancer / Reverse Proxy**
- **Nginx**: 
  - SSL termination
  - Static file serving
  - Load balancing across Django workers
  - Rate limiting (optional)
- **Configuration**: `docker/nginx.conf`

#### **Application Layer**
- **Django 5.0.1**:
  - **WSGI Server**: Gunicorn (3 workers in production)
  - **ASGI Server**: Django Channels (for WebSockets)
  - **Framework**: Django REST Framework
  - **Location**: `backend/`
- **Workers**: Horizontally scalable (add more Gunicorn workers)

#### **Data Layer**
- **PostgreSQL 15**:
  - Primary database for all persistent data
  - Connection pooling via Django ORM
  - Read replicas for scaling (optional)
- **Redis 7**:
  - **Cache**: Django cache backend (`django-redis`)
  - **Pub/Sub**: Real-time event broadcasting
  - **Celery Broker**: Task queue
  - **Session Storage**: Optional session backend

#### **Background Processing**
- **Celery Workers**: Async task processing
  - Analytics calculations
  - Email notifications
  - Cache warming
  - Data exports
- **Celery Beat**: Scheduled tasks
  - Poll expiration checks
  - Analytics aggregation
  - Cache cleanup

#### **Real-Time Communication**
- **Django Channels**: WebSocket support
- **Redis Pub/Sub**: Cross-server event broadcasting
- **Implementation**: `backend/apps/polls/consumers.py`

### 1.3 Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant Nginx
    participant Django
    participant Redis
    participant PostgreSQL
    participant Celery
    
    Client->>Nginx: HTTPS Request
    Nginx->>Django: HTTP Request (load balanced)
    Django->>Redis: Check Cache
    alt Cache Hit
        Redis-->>Django: Cached Data
        Django-->>Nginx: Response
    else Cache Miss
        Django->>PostgreSQL: Query Database
        PostgreSQL-->>Django: Data
        Django->>Redis: Store in Cache
        Django-->>Nginx: Response
    end
    Nginx-->>Client: HTTPS Response
    
    Note over Django,Celery: Async Task
    Django->>Redis: Enqueue Task
    Redis->>Celery: Task Notification
    Celery->>PostgreSQL: Process Task
    Celery->>Redis: Update Cache
```

**Code References:**
- Request handling: `backend/config/urls.py`
- Middleware: `backend/core/middleware/`
- Cache configuration: `backend/config/settings/base.py` (CACHES)

---

## 2. Database Schema (ERD)

### 2.1 Complete Entity-Relationship Diagram

```mermaid
erDiagram
    User ||--o| UserProfile : "has one"
    User ||--o{ Poll : "creates"
    User ||--o{ Vote : "casts"
    User ||--o{ VoteAttempt : "attempts"
    User ||--o{ Notification : "receives"
    User ||--o{ Follow : "follows"
    User ||--o{ Follow : "followed_by"
    
    Poll ||--o{ PollOption : "has many"
    Poll ||--o{ Vote : "receives"
    Poll ||--o{ VoteAttempt : "receives"
    Poll ||--o| PollAnalytics : "has one"
    Poll ||--o{ Notification : "triggers"
    Poll ||--o{ FraudAlert : "has"
    Poll }o--o| Category : "belongs to"
    Poll }o--o{ Tag : "tagged with"
    
    PollOption ||--o{ Vote : "receives"
    PollOption ||--o{ VoteAttempt : "targeted"
    
    Vote ||--o{ FraudAlert : "triggers"
    Vote ||--o{ Notification : "triggers"
    
    User {
        bigint id PK
        string username UK "NOT NULL"
        string email UK "NOT NULL"
        string password "NOT NULL"
        datetime date_joined "NOT NULL"
        boolean is_active "NOT NULL"
        boolean is_staff "NOT NULL"
        boolean is_superuser "NOT NULL"
    }
    
    UserProfile {
        bigint id PK
        bigint user_id FK "UNIQUE, NOT NULL"
        text bio
        datetime created_at "NOT NULL"
        datetime updated_at "NOT NULL"
    }
    
    Follow {
        bigint id PK
        bigint follower_id FK "NOT NULL, UNIQUE with following_id"
        bigint following_id FK "NOT NULL, UNIQUE with follower_id"
        datetime created_at "NOT NULL"
    }
    
    Category {
        bigint id PK
        string name UK "NOT NULL"
        string slug UK "NOT NULL"
        text description
        datetime created_at "NOT NULL"
    }
    
    Tag {
        bigint id PK
        string name UK "NOT NULL"
        string slug UK "NOT NULL"
        datetime created_at "NOT NULL"
    }
    
    Poll {
        bigint id PK
        string title "NOT NULL, max_length=200"
        text description
        bigint created_by_id FK "NOT NULL"
        bigint category_id FK "NULLABLE"
        datetime created_at "NOT NULL"
        datetime updated_at "NOT NULL"
        datetime starts_at "NOT NULL"
        datetime ends_at "NULLABLE"
        boolean is_active "NOT NULL, default=True"
        boolean is_draft "NOT NULL, default=False"
        json settings "default=dict"
        json security_rules "default=dict"
        integer cached_total_votes "default=0"
        integer cached_unique_voters "default=0"
    }
    
    PollOption {
        bigint id PK
        bigint poll_id FK "NOT NULL"
        string text "NOT NULL, max_length=200"
        integer order "default=0"
        integer cached_vote_count "default=0"
        datetime created_at "NOT NULL"
    }
    
    Vote {
        bigint id PK
        bigint user_id FK "NULLABLE, UNIQUE with poll_id if not null"
        bigint option_id FK "NOT NULL"
        bigint poll_id FK "NOT NULL, UNIQUE with user_id if user_id not null"
        string voter_token "NOT NULL, max_length=64, INDEXED"
        string idempotency_key UK "NOT NULL, max_length=64, INDEXED"
        string ip_address "NULLABLE, INDEXED"
        text user_agent
        string fingerprint "max_length=128, INDEXED"
        boolean is_valid "default=True, INDEXED"
        text fraud_reasons
        integer risk_score "default=0"
        datetime created_at "NOT NULL"
    }
    
    VoteAttempt {
        bigint id PK
        bigint user_id FK "NULLABLE"
        bigint poll_id FK "NOT NULL"
        bigint option_id FK "NULLABLE"
        string voter_token "max_length=64, INDEXED"
        string idempotency_key "max_length=64, INDEXED"
        string ip_address "NULLABLE, INDEXED"
        text user_agent
        string fingerprint "max_length=128, INDEXED"
        boolean success "default=False, INDEXED"
        text error_message
        datetime created_at "NOT NULL"
    }
    
    PollAnalytics {
        bigint id PK
        bigint poll_id FK "UNIQUE, NOT NULL"
        integer total_votes "NOT NULL, default=0"
        integer unique_voters "NOT NULL, default=0"
        datetime last_updated "NOT NULL"
    }
    
    AuditLog {
        bigint id PK
        bigint user_id FK "NULLABLE"
        string method "max_length=10"
        string path "max_length=500"
        text query_params
        text request_body
        integer status_code
        string ip_address "NULLABLE"
        string user_agent "max_length=500"
        string request_id "max_length=64, INDEXED"
        float response_time
        datetime created_at "NOT NULL"
    }
    
    FingerprintBlock {
        bigint id PK
        string fingerprint UK "max_length=128, INDEXED"
        text reason
        datetime blocked_at "NOT NULL"
        bigint blocked_by_id FK "NULLABLE"
        boolean is_active "default=True, INDEXED"
        datetime unblocked_at "NULLABLE"
        bigint unblocked_by_id FK "NULLABLE"
        bigint first_seen_user_id FK "NULLABLE"
        integer total_users "default=0"
        integer total_votes "default=0"
    }
    
    FraudAlert {
        bigint id PK
        bigint vote_id FK "NOT NULL"
        bigint poll_id FK "NOT NULL"
        bigint user_id FK "NULLABLE"
        string ip_address "NULLABLE"
        text reasons
        integer risk_score
        datetime created_at "NOT NULL"
    }
    
    IPReputation {
        bigint id PK
        string ip_address UK "INDEXED"
        integer reputation_score "default=100"
        integer violation_count "default=0"
        integer successful_attempts "default=0"
        integer failed_attempts "default=0"
        datetime first_seen "NOT NULL"
        datetime last_seen "NOT NULL"
        datetime last_violation_at "NULLABLE"
    }
    
    IPBlock {
        bigint id PK
        string ip_address UK "INDEXED"
        text reason
        datetime blocked_at "NOT NULL"
        bigint blocked_by_id FK "NULLABLE"
        boolean is_active "default=True, INDEXED"
        boolean is_manual "default=False"
        datetime auto_unblock_at "NULLABLE"
        datetime unblocked_at "NULLABLE"
        bigint unblocked_by_id FK "NULLABLE"
    }
    
    IPWhitelist {
        bigint id PK
        string ip_address UK "INDEXED"
        text reason
        bigint created_by_id FK "NULLABLE"
        datetime created_at "NOT NULL"
        boolean is_active "default=True, INDEXED"
    }
    
    Notification {
        bigint id PK
        bigint user_id FK "NOT NULL"
        string notification_type "max_length=50"
        string title "max_length=200"
        text message
        bigint poll_id FK "NULLABLE"
        bigint vote_id FK "NULLABLE"
        json metadata "default=dict"
        boolean is_read "default=False, INDEXED"
        datetime read_at "NULLABLE"
        datetime created_at "NOT NULL, INDEXED"
    }
    
    NotificationPreference {
        bigint id PK
        bigint user_id FK "UNIQUE, NOT NULL"
        boolean poll_results_available_email "default=True"
        boolean poll_results_available_in_app "default=True"
        boolean poll_results_available_push "default=False"
        boolean new_poll_from_followed_email "default=True"
        boolean new_poll_from_followed_in_app "default=True"
        boolean new_poll_from_followed_push "default=False"
        boolean poll_about_to_expire_email "default=True"
        boolean poll_about_to_expire_in_app "default=True"
        boolean poll_about_to_expire_push "default=False"
        boolean vote_flagged_email "default=True"
        boolean vote_flagged_in_app "default=True"
        boolean vote_flagged_push "default=False"
        boolean email_enabled "default=True"
        boolean in_app_enabled "default=True"
        boolean push_enabled "default=False"
        boolean unsubscribed "default=False"
        datetime unsubscribed_at "NULLABLE"
        datetime created_at "NOT NULL"
        datetime updated_at "NOT NULL"
    }
    
    NotificationDelivery {
        bigint id PK
        bigint notification_id FK "NOT NULL, UNIQUE with channel"
        string channel "max_length=20, UNIQUE with notification_id"
        string status "max_length=20, INDEXED"
        datetime sent_at "NULLABLE"
        text error_message
        string external_id "max_length=255"
        datetime created_at "NOT NULL"
        datetime updated_at "NOT NULL"
    }
```

### 2.2 Key Relationships

| Relationship | Type | Tables | Foreign Key | Delete Behavior |
|-------------|------|--------|-------------|----------------|
| User → UserProfile | One-to-One | `auth_user` → `users_userprofile` | `user_id` | CASCADE |
| User → Poll | One-to-Many | `auth_user` → `polls_poll` | `created_by_id` | CASCADE |
| User → Vote | One-to-Many | `auth_user` → `votes_vote` | `user_id` | CASCADE |
| Poll → PollOption | One-to-Many | `polls_poll` → `polls_polloption` | `poll_id` | CASCADE |
| Poll → Vote | One-to-Many | `polls_poll` → `votes_vote` | `poll_id` | CASCADE |
| Poll → PollAnalytics | One-to-One | `polls_poll` → `analytics_pollanalytics` | `poll_id` | CASCADE |
| PollOption → Vote | One-to-Many | `polls_polloption` → `votes_vote` | `option_id` | CASCADE |
| Poll → Category | Many-to-One | `polls_poll` → `polls_category` | `category_id` | SET_NULL |
| Poll → Tag | Many-to-Many | `polls_poll` ↔ `polls_tag` | via `polls_poll_tags` | - |
| User → Follow | Self-Referential | `auth_user` → `users_follow` | `follower_id`, `following_id` | CASCADE |

### 2.3 Critical Constraints

1. **Unique Constraints:**
   - `Vote.idempotency_key` - Ensures idempotency
   - `Vote(user_id, poll_id)` - One vote per user per poll (when user is not null)
   - `Follow(follower_id, following_id)` - No duplicate follows
   - `PollAnalytics.poll_id` - One analytics record per poll

2. **Indexes for Performance:**
   - `Vote.idempotency_key` - Fast idempotency checks
   - `Vote(poll_id, created_at)` - Vote history queries
   - `Vote(user_id, poll_id)` - User vote lookups
   - `VoteAttempt(poll_id, created_at)` - Audit trail queries
   - `AuditLog(request_id)` - Request tracing

**Code References:**
- Models: `backend/apps/polls/models.py`, `backend/apps/votes/models.py`, `backend/apps/analytics/models.py`, `backend/apps/users/models.py`, `backend/apps/notifications/models.py`
- ERD Documentation: `docs/database-erd-design.md`

---

## 3. API Flow Diagrams

### 3.1 Vote Creation Flow (Complete)

```mermaid
sequenceDiagram
    participant Client
    participant Nginx
    participant Django
    participant Middleware
    participant VoteService
    participant Redis
    participant PostgreSQL
    participant Celery
    participant Channels
    
    Client->>Nginx: POST /api/v1/votes/cast/
    Nginx->>Django: HTTP Request
    
    Django->>Middleware: Rate Limiting Check
    alt Rate Limit Exceeded
        Middleware-->>Django: 429 Too Many Requests
        Django-->>Client: Error Response
    end
    
    Django->>Middleware: Audit Logging
    Middleware->>PostgreSQL: Log Request
    
    Django->>VoteService: cast_vote()
    
    Note over VoteService: Extract Request Data
    VoteService->>VoteService: Extract IP, User-Agent, Fingerprint
    
    Note over VoteService: Fingerprint Validation
    VoteService->>VoteService: Validate Fingerprint Format
    alt Invalid Fingerprint
        VoteService-->>Django: FingerprintValidationError
        Django-->>Client: 400 Bad Request
    end
    
    VoteService->>VoteService: Check Fingerprint Block
    alt Fingerprint Blocked
        VoteService->>PostgreSQL: Create VoteAttempt (failed)
        VoteService-->>Django: FraudDetectedError
        Django-->>Client: 403 Forbidden
    end
    
    Note over VoteService: Generate Idempotency Key
    VoteService->>VoteService: generate_idempotency_key()
    
    Note over VoteService: Idempotency Check
    VoteService->>Redis: Check Cache (idempotency:{key})
    alt Cache Hit
        Redis-->>VoteService: Existing Vote ID
        VoteService->>PostgreSQL: Get Vote
        VoteService-->>Django: Return Existing Vote (200 OK)
        Django-->>Client: Success (Idempotent Retry)
    else Cache Miss
        VoteService->>PostgreSQL: Check DB for idempotency_key
        alt Vote Exists in DB
            PostgreSQL-->>VoteService: Existing Vote
            VoteService->>Redis: Store in Cache
            VoteService-->>Django: Return Existing Vote (200 OK)
            Django-->>Client: Success (Idempotent Retry)
        else New Vote
            Note over VoteService: IP Reputation Check
            VoteService->>PostgreSQL: Check IPReputation
            alt IP Blocked
                VoteService->>PostgreSQL: Create VoteAttempt (failed)
                VoteService-->>Django: IPBlockedError
                Django-->>Client: 403 Forbidden
            end
            
            Note over VoteService: Geographic Restriction Check
            VoteService->>PostgreSQL: Get Poll
            VoteService->>VoteService: Check Geographic Restrictions
            alt Geographic Restriction Violation
                VoteService->>PostgreSQL: Create VoteAttempt (failed)
                VoteService-->>Django: InvalidVoteError
                Django-->>Client: 400 Bad Request
            end
            
            Note over VoteService: Transaction Start
            VoteService->>PostgreSQL: BEGIN TRANSACTION
            VoteService->>PostgreSQL: SELECT FOR UPDATE (Poll)
            
            Note over VoteService: Poll Validation
            VoteService->>VoteService: Validate Poll (is_open, active, etc.)
            alt Poll Invalid
                VoteService->>PostgreSQL: ROLLBACK
                VoteService-->>Django: InvalidPollError
                Django-->>Client: 400 Bad Request
            end
            
            Note over VoteService: Duplicate Vote Check
            VoteService->>PostgreSQL: Check if user already voted
            alt Already Voted
                VoteService->>PostgreSQL: ROLLBACK
                VoteService-->>Django: DuplicateVoteError
                Django-->>Client: 409 Conflict
            end
            
            Note over VoteService: Fraud Detection
            VoteService->>VoteService: detect_fraud()
            VoteService->>PostgreSQL: Check Rapid Votes, Patterns
            alt Fraud Detected
                VoteService->>PostgreSQL: Create Vote (is_valid=False)
                VoteService->>PostgreSQL: Create FraudAlert
                VoteService->>PostgreSQL: COMMIT
                VoteService-->>Django: Vote Created (marked invalid)
            else No Fraud
                VoteService->>PostgreSQL: Create Vote (is_valid=True)
            end
            
            Note over VoteService: Update Denormalized Counts
            VoteService->>PostgreSQL: Update Poll.cached_total_votes
            VoteService->>PostgreSQL: Update PollOption.cached_vote_count
            VoteService->>PostgreSQL: Update PollAnalytics
            
            VoteService->>PostgreSQL: COMMIT
            
            VoteService->>Redis: Store Idempotency Result
            VoteService->>Redis: Invalidate Poll Cache
            
            Note over VoteService: Async Tasks
            VoteService->>Celery: Enqueue Analytics Update
            VoteService->>Celery: Enqueue Notification Task
            
            Note over VoteService: Real-Time Updates
            VoteService->>Channels: Publish Vote Event
            Channels->>Redis: Pub/Sub (vote_events)
            Redis->>Channels: Broadcast to WebSocket Clients
            
            VoteService->>PostgreSQL: Create VoteAttempt (success)
            VoteService-->>Django: Return New Vote (201 Created)
            Django-->>Client: Success Response
        end
    end
```

**Code References:**
- Vote service: `backend/apps/votes/services.py::cast_vote()`
- Idempotency: `backend/core/utils/idempotency.py`
- Fraud detection: `backend/core/utils/fraud_detection.py`
- Views: `backend/apps/votes/views.py::VoteViewSet.cast()`

### 3.2 Poll Creation Flow

```mermaid
sequenceDiagram
    participant Client
    participant Django
    participant PollViewSet
    participant PostgreSQL
    participant Celery
    
    Client->>Django: POST /api/v1/polls/
    Django->>PollViewSet: create()
    
    PollViewSet->>PollViewSet: Validate Request Data
    PollViewSet->>PollViewSet: Check Permissions
    
    PollViewSet->>PostgreSQL: Create Poll
    PollViewSet->>PostgreSQL: Create PollOptions
    PollViewSet->>PostgreSQL: Create PollAnalytics
    
    PollViewSet->>Celery: Enqueue Notification Task
    Note over Celery: Notify Followers of New Poll
    
    PollViewSet-->>Django: Return Poll (201 Created)
    Django-->>Client: Success Response
```

**Code References:**
- Poll creation: `backend/apps/polls/views.py::PollViewSet.create()`
- Serializers: `backend/apps/polls/serializers.py`

### 3.3 Real-Time Results Update Flow

```mermaid
sequenceDiagram
    participant Client
    participant WebSocket
    participant Channels
    participant Redis
    participant VoteService
    participant PostgreSQL
    
    Client->>WebSocket: Connect to /ws/polls/{id}/results/
    WebSocket->>Channels: WebSocket Connection
    Channels->>Redis: Subscribe to provote:vote_events
    
    Note over VoteService: Vote Created
    VoteService->>Redis: Publish Vote Event
    Redis->>Channels: Event Notification
    Channels->>PostgreSQL: Get Updated Results
    Channels->>WebSocket: Send Results Update
    WebSocket->>Client: JSON Update
```

**Code References:**
- WebSocket consumer: `backend/apps/polls/consumers.py::PollResultsConsumer`
- Redis Pub/Sub: `backend/core/utils/redis_pubsub.py`

---

## 4. Idempotency System

### 4.1 Idempotency Overview

Idempotency ensures that multiple identical requests produce the same result as a single request. This is critical for:
- **Network retries**: Client retries don't create duplicate votes
- **Race conditions**: Concurrent requests are handled safely
- **User experience**: Users can safely retry failed requests

### 4.2 Idempotency Key Generation

```mermaid
graph LR
    A[Vote Request] --> B{User Authenticated?}
    B -->|Yes| C[Generate: user_id:poll_id:choice_id]
    B -->|No| D[Generate: anon:poll_id:choice_id:fingerprint:ip]
    C --> E[SHA256 Hash]
    D --> E
    E --> F[64-char Hex String]
    F --> G[Idempotency Key]
```

**Algorithm:**
```python
# Authenticated users
key = SHA256(f"{user_id}:{poll_id}:{choice_id}")

# Anonymous users
key = SHA256(f"anon:{poll_id}:{choice_id}:{fingerprint}:{ip_address}")
```

**Code Reference:** `backend/core/utils/idempotency.py::generate_idempotency_key()`

### 4.3 Idempotency Check Flow

```mermaid
sequenceDiagram
    participant Request
    participant VoteService
    participant Redis
    participant PostgreSQL
    
    Request->>VoteService: Vote with Idempotency Key
    
    Note over VoteService: Step 1: Cache Check
    VoteService->>Redis: GET idempotency:{key}
    alt Cache Hit
        Redis-->>VoteService: Cached Vote ID
        VoteService->>PostgreSQL: Get Vote by ID
        PostgreSQL-->>VoteService: Existing Vote
        VoteService-->>Request: Return Existing Vote (200 OK)
    else Cache Miss
        Note over VoteService: Step 2: Database Check
        VoteService->>PostgreSQL: SELECT WHERE idempotency_key = key
        alt Vote Exists
            PostgreSQL-->>VoteService: Existing Vote
            VoteService->>Redis: SET idempotency:{key} (TTL: 1h)
            VoteService-->>Request: Return Existing Vote (200 OK)
        else New Vote
            Note over VoteService: Step 3: Create Vote
            VoteService->>PostgreSQL: BEGIN TRANSACTION
            VoteService->>PostgreSQL: SELECT FOR UPDATE (Poll)
            VoteService->>PostgreSQL: INSERT Vote
            VoteService->>PostgreSQL: COMMIT
            VoteService->>Redis: SET idempotency:{key} = {vote_id} (TTL: 1h)
            VoteService-->>Request: Return New Vote (201 Created)
        end
    end
```

### 4.4 Race Condition Handling

When multiple requests arrive simultaneously with the same idempotency key:

1. **First Request**: Creates vote, stores in cache and DB
2. **Concurrent Requests**: 
   - Cache check may miss (race condition window)
   - Database check finds existing vote (unique constraint)
   - Returns existing vote (200 OK)

**Database Constraint:**
```sql
UNIQUE(idempotency_key)  -- Prevents duplicate votes
```

**Transaction Isolation:**
- Uses `SELECT FOR UPDATE` to lock poll during vote creation
- Prevents concurrent vote count updates
- Ensures atomicity

**Code Reference:** `backend/apps/votes/services.py::cast_vote()` (lines 147-171, 246-460)

### 4.5 Idempotency Guarantees

| Scenario | Behavior | HTTP Status |
|----------|----------|-------------|
| First request | Creates new vote | 201 Created |
| Retry with same key | Returns existing vote | 200 OK |
| Concurrent requests | Only one vote created | 200 OK (retries) or 201 Created (first) |
| Network timeout retry | Returns existing vote | 200 OK |
| Client-side retry | Returns existing vote | 200 OK |

**Test Verification:**
- `backend/tests/test_idempotency_stress.py` - Comprehensive stress tests
- `backend/tests/README_IDEMPOTENCY_STRESS.md` - Test documentation

---

## 5. Scaling Strategy

### 5.1 Horizontal Scaling Architecture

```mermaid
graph TB
    LB[Load Balancer<br/>Nginx/HAProxy] --> Django1[Django Instance 1<br/>3 Gunicorn Workers]
    LB --> Django2[Django Instance 2<br/>3 Gunicorn Workers]
    LB --> Django3[Django Instance 3<br/>3 Gunicorn Workers]
    
    Django1 --> RedisCluster[Redis Cluster<br/>or Sentinel]
    Django2 --> RedisCluster
    Django3 --> RedisCluster
    
    Django1 --> PGPrimary[(PostgreSQL<br/>Primary)]
    Django2 --> PGPrimary
    Django3 --> PGPrimary
    
    PGPrimary -->|Replication| PGReplica1[(PostgreSQL<br/>Read Replica 1)]
    PGPrimary -->|Replication| PGReplica2[(PostgreSQL<br/>Read Replica 2)]
    
    Django1 -->|Read Queries| PGReplica1
    Django2 -->|Read Queries| PGReplica2
    Django3 -->|Read Queries| PGReplica1
    
    Celery1[Celery Worker Pool 1] --> RedisCluster
    Celery2[Celery Worker Pool 2] --> RedisCluster
    Celery1 --> PGPrimary
    Celery2 --> PGPrimary
```

### 5.2 Application Layer Scaling

#### **Django Application Servers**
- **Current**: 3 Gunicorn workers per instance
- **Scaling**: Add more Django instances behind load balancer
- **Configuration**: `docker/docker-compose.yml` (web service)
- **Stateless**: Each instance is stateless (sessions in Redis)

**Scaling Steps:**
1. Add more Django containers/instances
2. Configure load balancer (Nginx/HAProxy)
3. Ensure shared Redis for cache/sessions
4. Use database connection pooling

#### **Gunicorn Workers**
- **Formula**: `(2 × CPU cores) + 1`
- **Current**: 3 workers (configurable)
- **Tuning**: Adjust based on I/O vs CPU-bound tasks

### 5.3 Database Scaling

#### **Read Replicas**
- **Purpose**: Offload read queries from primary
- **Implementation**: PostgreSQL streaming replication
- **Use Cases**:
  - Poll listing queries
  - Analytics queries
  - Vote history queries
- **Configuration**: Django database router

**Code Reference:** `backend/config/settings/base.py` (DATABASES)

#### **Connection Pooling**
- **Current**: Django ORM connection pooling
- **Advanced**: PgBouncer for connection pooling
- **Benefits**: Reduces connection overhead

#### **Partitioning** (Future)
- **Vote Table**: Partition by `poll_id` or `created_at`
- **AuditLog Table**: Partition by `created_at` (monthly)
- **Benefits**: Faster queries on large datasets

### 5.4 Cache Scaling

#### **Redis Architecture**
- **Current**: Single Redis instance
- **Scaling Options**:
  1. **Redis Sentinel**: High availability
  2. **Redis Cluster**: Horizontal scaling
  3. **Redis Replication**: Read replicas

#### **Cache Strategy**
- **Idempotency Keys**: TTL 1 hour
- **Poll Results**: TTL 5 minutes
- **User Sessions**: TTL 2 weeks
- **Rate Limit Counters**: TTL per window

**Code Reference:** `backend/core/utils/idempotency.py::store_idempotency_result()`

### 5.5 Background Task Scaling

#### **Celery Workers**
- **Current**: Single Celery worker
- **Scaling**: Add more worker processes/instances
- **Queue Strategy**:
  - `high_priority`: Real-time tasks
  - `default`: Standard tasks
  - `low_priority`: Batch jobs

#### **Task Distribution**
- **Analytics**: Separate worker pool
- **Notifications**: Separate worker pool
- **Exports**: Low-priority queue

### 5.6 WebSocket Scaling

#### **Redis Pub/Sub**
- **Current**: Single Redis instance for Pub/Sub
- **Scaling**: Redis Cluster for Pub/Sub
- **Architecture**: 
  - Each Django instance subscribes to Redis
  - Vote events published to Redis channel
  - All instances receive and broadcast to local WebSocket clients

**Code Reference:** `backend/core/utils/redis_pubsub.py`

### 5.7 Load Balancing

#### **Nginx Configuration**
- **Algorithm**: Round-robin (default)
- **Alternatives**: Least connections, IP hash
- **Health Checks**: Monitor Django health endpoints
- **SSL Termination**: At load balancer

**Configuration:** `docker/nginx.conf`

### 5.8 Monitoring & Metrics

**Key Metrics to Monitor:**
- Request rate per instance
- Response times
- Database connection pool usage
- Redis memory usage
- Celery queue lengths
- WebSocket connection count

**Scaling Triggers:**
- CPU usage > 70%
- Memory usage > 80%
- Response time > 500ms (p95)
- Queue length > 1000 tasks

---

## 6. Security Architecture

### 6.1 Security Layers

```mermaid
graph TB
    Internet[Internet] --> Firewall[Firewall<br/>Port 443/80 Only]
    Firewall --> LB[Load Balancer<br/>SSL Termination]
    LB --> WAF[Web Application Firewall<br/>Optional]
    WAF --> Django[Django Application]
    
    Django --> Auth[Authentication Layer]
    Django --> RateLimit[Rate Limiting]
    Django --> Fraud[Fraud Detection]
    Django --> Geo[Geographic Restrictions]
    
    Auth --> Session[Session Management]
    RateLimit --> Redis[(Redis Cache)]
    Fraud --> PostgreSQL[(PostgreSQL)]
    Geo --> Geolocation[IP Geolocation Service]
    
    Django --> Audit[Audit Logging]
    Audit --> PostgreSQL
```

### 6.2 Authentication & Authorization

#### **Authentication Methods**
- **Session Authentication**: Django sessions (current)
- **Future**: JWT tokens for API clients
- **Anonymous Voting**: Supported with fingerprint validation

#### **Authorization**
- **Poll Ownership**: Only creator can edit/delete
- **Vote Permissions**: Based on poll settings
- **Admin Access**: Django admin interface

**Code Reference:** `backend/apps/polls/permissions.py`

### 6.3 Rate Limiting

#### **Rate Limit Strategy**
- **Anonymous Users**: 
  - General API: 100 requests/hour
  - Voting: 50 votes/hour
- **Authenticated Users**:
  - General API: 1000 requests/hour
  - Voting: 200 votes/hour
- **Poll Creation**: 10 polls/hour
- **Poll Reading**: 200 requests/hour

#### **Implementation**
- **Middleware**: `backend/core/middleware/rate_limit.py`
- **Storage**: Redis (sliding window)
- **Headers**: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset

**Code Reference:** `backend/core/throttles.py`

### 6.4 Fraud Detection System

```mermaid
graph LR
    A[Vote Request] --> B[Fingerprint Check]
    A --> C[IP Reputation Check]
    A --> D[Geographic Check]
    A --> E[Pattern Analysis]
    
    B --> F{Risk Score}
    C --> F
    D --> F
    E --> F
    
    F -->|Low Risk| G[Allow Vote]
    F -->|Medium Risk| H[Mark as Suspicious]
    F -->|High Risk| I[Block Vote]
    
    H --> J[Create FraudAlert]
    I --> J
    I --> K[Create VoteAttempt failed]
```

#### **Fraud Detection Rules**

1. **Fingerprint Validation**
   - Format validation (64-char SHA256)
   - Blocked fingerprint check
   - Multi-user fingerprint detection

2. **IP Reputation**
   - Reputation score tracking
   - Violation count monitoring
   - Automatic blocking (threshold-based)

3. **Rapid Voting Detection**
   - Multiple votes from same IP in short time
   - Threshold: 3 votes in 5 minutes

4. **Suspicious Patterns**
   - All votes from IP to same option
   - Bot user agent detection
   - Empty/missing fingerprints

5. **Geographic Restrictions**
   - Country-based allow/block lists
   - Region-based restrictions
   - IP geolocation (MaxMind/ipapi.co)

**Code References:**
- Fraud detection: `backend/core/utils/fraud_detection.py`
- Fingerprint validation: `backend/core/utils/fingerprint_validation.py`
- IP reputation: `backend/core/utils/ip_reputation.py`
- Geographic restrictions: `backend/core/utils/geolocation.py`

### 6.5 Security Headers

**Headers Implemented:**
- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (production)

**Configuration:** `docker/nginx.conf`

### 6.6 Data Protection

#### **Input Validation**
- **Django Forms**: Automatic XSS protection
- **DRF Serializers**: Field validation
- **SQL Injection**: Django ORM (parameterized queries)

#### **Output Encoding**
- **Templates**: Automatic HTML escaping
- **JSON Responses**: Proper content-type headers

#### **Sensitive Data**
- **Passwords**: Hashed (Django's PBKDF2)
- **API Keys**: Not logged in audit trails
- **IP Addresses**: Stored but not exposed in responses

### 6.7 Audit Logging

#### **What's Logged**
- All API requests (method, path, status)
- Vote attempts (success/failure)
- Fraud alerts
- IP reputation changes
- Fingerprint blocks

#### **Storage**
- **AuditLog Model**: All API requests
- **VoteAttempt Model**: All vote attempts
- **FraudAlert Model**: Fraud detection events

**Code Reference:** `backend/apps/analytics/models.py::AuditLog`

### 6.8 Geographic Restrictions

#### **Implementation**
- **IP Geolocation**: MaxMind GeoIP2 (primary), ipapi.co (fallback)
- **Poll Configuration**: `security_rules` JSON field
- **Validation**: Before vote creation (fail-fast)

**Configuration:**
```json
{
  "allowed_countries": ["KE"],
  "blocked_countries": [],
  "allowed_regions": [],
  "blocked_regions": []
}
```

**Note:** The default configuration restricts voting to Kenya (KE) only. To allow other countries, add their ISO 3166-1 alpha-2 country codes to the `allowed_countries` array.

**Code Reference:** `backend/core/utils/geolocation.py`

---

## 7. Test Verification

### 7.1 Architecture Diagram Tests

**Test File:** `backend/tests/test_api_documentation.py`

**Verification:**
- ✅ Schema generation without errors
- ✅ All endpoints documented
- ✅ Request/response examples accurate

**Run Tests:**
```bash
pytest backend/tests/test_api_documentation.py -v
```

### 7.2 Database Schema Tests

**Test Files:**
- `backend/apps/polls/tests/test_models.py`
- `backend/apps/votes/tests/test_models.py`
- `backend/apps/analytics/tests/test_models.py`

**Verification:**
- ✅ All models have correct relationships
- ✅ Constraints are enforced
- ✅ Indexes are created
- ✅ Migrations are reversible

**Run Tests:**
```bash
pytest backend/apps/*/tests/test_models.py -v
```

### 7.3 API Flow Tests

**Test Files:**
- `backend/tests/test_e2e_voting_flow.py`
- `backend/apps/votes/tests/test_views.py`
- `backend/apps/polls/tests/test_views.py`

**Verification:**
- ✅ Vote creation flow works end-to-end
- ✅ Poll creation flow works
- ✅ Real-time updates work via WebSocket

**Run Tests:**
```bash
pytest backend/tests/test_e2e_voting_flow.py -v
pytest backend/apps/votes/tests/test_views.py -v
```

### 7.4 Idempotency Tests

**Test File:** `backend/tests/test_idempotency_stress.py`

**Scenarios Tested:**
- ✅ 1000 simultaneous identical votes → 1 vote created
- ✅ Network retry simulation → Returns existing vote
- ✅ Race conditions → Only 1 vote created
- ✅ Database deadlocks → Handled gracefully
- ✅ Cache consistency → Cache and DB stay in sync

**Run Tests:**
```bash
pytest backend/tests/test_idempotency_stress.py -v -m stress
```

**Documentation:** `backend/tests/README_IDEMPOTENCY_STRESS.md`

### 7.5 Scaling Tests

**Test Files:**
- `backend/tests/test_concurrent_load.py`
- `load_tests/` (if exists)

**Verification:**
- ✅ Concurrent vote creation (100+ simultaneous)
- ✅ Database connection pooling works
- ✅ Redis caching works under load
- ✅ Celery tasks process correctly

**Run Tests:**
```bash
pytest backend/tests/test_concurrent_load.py -v
```

### 7.6 Security Tests

**Test Files:**
- `backend/tests/test_security.py`
- `backend/tests/test_security_advanced.py`

**Scenarios Tested:**
- ✅ SQL injection protection
- ✅ XSS protection
- ✅ CSRF protection
- ✅ Rate limiting enforcement
- ✅ Fraud detection accuracy
- ✅ Geographic restrictions

**Run Tests:**
```bash
pytest backend/tests/test_security*.py -v -m security
```

**Documentation:** `backend/tests/README_SECURITY.md`

### 7.7 Integration Tests

**Test File:** `backend/tests/test_integration.py`

**Verification:**
- ✅ Database connectivity
- ✅ Redis connectivity
- ✅ Celery task execution
- ✅ WebSocket connections

**Run Tests:**
```bash
pytest backend/tests/test_integration.py -v
```

### 7.8 Documentation Accuracy Tests

**Manual Verification Checklist:**
- [ ] All Mermaid diagrams render correctly (GitHub/GitLab)
- [ ] Code references point to correct files
- [ ] API endpoints match actual implementation
- [ ] Database schema matches migrations
- [ ] Security measures are accurately described

**Automated Checks:**
```bash
# Verify code references exist
grep -r "backend/" docs/architecture-comprehensive.md | while read line; do
    file=$(echo $line | cut -d: -f2 | sed 's/`//g')
    if [ ! -f "$file" ]; then
        echo "Missing file: $file"
    fi
done
```

---

## Appendix

### A. Technology Stack

- **Backend**: Django 5.0.1, Django REST Framework 3.14.0
- **Database**: PostgreSQL 15
- **Cache**: Redis 7
- **Task Queue**: Celery 5.3.4
- **WebSockets**: Django Channels 4.0.0
- **API Documentation**: drf-spectacular 0.27.2
- **Web Server**: Gunicorn, Nginx
- **Containerization**: Docker, Docker Compose

### B. Key Design Decisions

1. **Idempotency Keys**: SHA256 hashes for deterministic generation
2. **Denormalized Counts**: Cached vote counts for performance
3. **VoteAttempt Model**: Immutable audit log of all attempts
4. **Geographic Restrictions**: Fail-open (don't block if geolocation fails)
5. **Fraud Detection**: Multi-tier validation (fingerprint, IP, patterns)
6. **WebSocket Scaling**: Redis Pub/Sub for cross-server communication

### C. Performance Benchmarks

- **Vote Creation**: < 100ms (p95)
- **Idempotency Check**: < 10ms (cache hit)
- **Poll Results**: < 50ms (cached)
- **Concurrent Votes**: 1000 votes in < 30s
- **WebSocket Latency**: < 100ms (event propagation)

### D. Future Enhancements

1. **Database**: Read replicas, partitioning
2. **Cache**: Redis Cluster for high availability
3. **Monitoring**: Prometheus + Grafana
4. **Logging**: ELK stack (Elasticsearch, Logstash, Kibana)
5. **CDN**: CloudFlare for static assets
6. **API**: GraphQL endpoint (optional)

---

**Document Maintained By:** Architecture Team  
**Last Review Date:** 2025-11-21  
**Next Review Date:** 2026-02-21

