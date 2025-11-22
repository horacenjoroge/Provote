# Database ERD Design

**Version:** 2.0  
**Last Updated:** 2025-11-22  
**Project:** Provote - Professional Voting Platform

## Overview

This document describes the Entity-Relationship Diagram (ERD) for the Provote voting platform database. The design focuses on data integrity, performance, and scalability for a voting system with idempotent operations, fraud detection, geographic restrictions, and comprehensive analytics.

## Entity-Relationship Diagram

### Visual ERD (Mermaid)

```mermaid
erDiagram
    User ||--o| UserProfile : "has one"
    User ||--o| NotificationPreference : "has one"
    User ||--o{ Poll : "creates"
    User ||--o{ Vote : "casts"
    User ||--o{ Follow : "follower"
    User ||--o{ Follow : "following"
    User ||--o{ Notification : "receives"
    User ||--o{ AuditLog : "generates"
    
    Poll ||--o{ PollOption : "has many"
    Poll ||--o{ Vote : "receives"
    Poll ||--o{ VoteAttempt : "receives"
    Poll ||--|| PollAnalytics : "has one"
    Poll ||--o{ Notification : "triggers"
    Poll ||--o{ FraudAlert : "has"
    Poll }o--o| Category : "belongs to"
    Poll }o--o{ Tag : "has tags"
    
    PollOption ||--o{ Vote : "receives"
    PollOption ||--o{ VoteAttempt : "target"
    
    Vote ||--o{ FraudAlert : "triggers"
    Vote ||--o{ Notification : "triggers"
    
    VoteAttempt {
        bigint id PK
        bigint user_id FK "NULLABLE"
        bigint poll_id FK "NOT NULL"
        bigint option_id FK "NULLABLE"
        string voter_token "INDEXED"
        string idempotency_key "INDEXED"
        inet ip_address "INDEXED"
        text user_agent
        string fingerprint "INDEXED"
        boolean success "NOT NULL"
        text error_message
        datetime created_at "NOT NULL"
    }
    
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
        bigint follower_id FK "NOT NULL"
        bigint following_id FK "NOT NULL"
        datetime created_at "INDEXED"
        UNIQUE "follower_id, following_id"
    }
    
    Poll {
        bigint id PK
        string title "NOT NULL, max_length=200"
        text description
        bigint created_by_id FK "NOT NULL"
        bigint category_id FK "NULLABLE"
        datetime created_at "NOT NULL, INDEXED"
        datetime updated_at "NOT NULL"
        datetime starts_at "NOT NULL"
        datetime ends_at "NULLABLE"
        boolean is_active "NOT NULL, default=True"
        boolean is_draft "NOT NULL, default=False"
        jsonb settings "default={}"
        jsonb security_rules "default={}"
        integer cached_total_votes "default=0"
        integer cached_unique_voters "default=0"
        INDEX "is_active, starts_at, ends_at"
        INDEX "is_draft, created_by_id"
        INDEX "category_id"
    }
    
    Category {
        bigint id PK
        string name UK "NOT NULL, max_length=100"
        string slug UK "NOT NULL, max_length=100, INDEXED"
        text description
        datetime created_at "NOT NULL"
    }
    
    Tag {
        bigint id PK
        string name UK "NOT NULL, max_length=50"
        string slug UK "NOT NULL, max_length=50, INDEXED"
        datetime created_at "NOT NULL"
        INDEX "name"
    }
    
    PollOption {
        bigint id PK
        bigint poll_id FK "NOT NULL"
        string text "NOT NULL, max_length=200"
        integer order "default=0"
        integer cached_vote_count "default=0"
        datetime created_at "NOT NULL"
        INDEX "poll_id, order"
    }
    
    Vote {
        bigint id PK
        bigint user_id FK "NULLABLE"
        bigint option_id FK "NOT NULL"
        bigint poll_id FK "NOT NULL"
        string voter_token "INDEXED, max_length=64"
        string idempotency_key UK "INDEXED, max_length=64"
        inet ip_address "INDEXED"
        text user_agent
        string fingerprint "INDEXED, max_length=128"
        boolean is_valid "default=True, INDEXED"
        text fraud_reasons
        integer risk_score "default=0"
        datetime created_at "NOT NULL, INDEXED"
        UNIQUE "user_id, poll_id" "where user_id IS NOT NULL"
        INDEX "poll_id, voter_token"
        INDEX "ip_address, created_at"
        INDEX "user_id, poll_id"
        INDEX "poll_id, created_at"
        INDEX "fingerprint, created_at"
        INDEX "is_valid, poll_id"
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
        integer status_code "NOT NULL"
        inet ip_address "INDEXED"
        string user_agent "max_length=500"
        string request_id "INDEXED, max_length=64"
        float response_time "NOT NULL"
        datetime created_at "NOT NULL, INDEXED"
        INDEX "user_id, created_at"
        INDEX "ip_address, created_at"
        INDEX "method, path, created_at"
    }
    
    Notification {
        bigint id PK
        bigint user_id FK "NOT NULL"
        string notification_type "max_length=50"
        string title "max_length=200"
        text message
        bigint poll_id FK "NULLABLE"
        bigint vote_id FK "NULLABLE"
        jsonb metadata "default={}"
        boolean is_read "default=False, INDEXED"
        datetime read_at
        datetime created_at "NOT NULL, INDEXED"
        INDEX "user_id, is_read, created_at"
        INDEX "notification_type, created_at"
        INDEX "poll_id, created_at"
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
        datetime unsubscribed_at
        datetime created_at "NOT NULL"
        datetime updated_at "NOT NULL"
    }
    
    NotificationDelivery {
        bigint id PK
        bigint notification_id FK "NOT NULL"
        string channel "max_length=20"
        string status "max_length=20, INDEXED, default='pending'"
        datetime sent_at
        text error_message
        string external_id "max_length=255"
        datetime created_at "NOT NULL"
        datetime updated_at "NOT NULL"
        UNIQUE "notification_id, channel"
        INDEX "status, created_at"
        INDEX "channel, status"
    }
    
    FraudAlert {
        bigint id PK
        bigint vote_id FK "NOT NULL"
        bigint poll_id FK "NOT NULL"
        bigint user_id FK "NULLABLE"
        inet ip_address
        text reasons "NOT NULL"
        integer risk_score "NOT NULL"
        datetime created_at "NOT NULL, INDEXED"
        INDEX "poll_id, created_at"
        INDEX "user_id, created_at"
        INDEX "ip_address, created_at"
        INDEX "risk_score, created_at"
    }
    
    IPReputation {
        bigint id PK
        inet ip_address UK "INDEXED"
        integer reputation_score "default=100"
        integer violation_count "default=0"
        integer successful_attempts "default=0"
        integer failed_attempts "default=0"
        datetime first_seen "NOT NULL"
        datetime last_seen "NOT NULL"
        datetime last_violation_at
        INDEX "reputation_score, last_seen"
        INDEX "violation_count, last_seen"
    }
    
    IPBlock {
        bigint id PK
        inet ip_address UK "INDEXED"
        text reason "NOT NULL"
        datetime blocked_at "NOT NULL"
        bigint blocked_by_id FK "NULLABLE"
        boolean is_active "default=True, INDEXED"
        boolean is_manual "default=False"
        datetime auto_unblock_at
        datetime unblocked_at
        bigint unblocked_by_id FK "NULLABLE"
        INDEX "ip_address, is_active"
        INDEX "is_active, auto_unblock_at"
        INDEX "is_manual, is_active"
    }
    
    FingerprintBlock {
        bigint id PK
        string fingerprint UK "INDEXED, max_length=128"
        text reason "NOT NULL"
        datetime blocked_at "NOT NULL"
        bigint blocked_by_id FK "NULLABLE"
        boolean is_active "default=True, INDEXED"
        datetime unblocked_at
        bigint unblocked_by_id FK "NULLABLE"
        bigint first_seen_user_id FK "NULLABLE"
        integer total_users "default=0"
        integer total_votes "default=0"
        INDEX "fingerprint, is_active"
        INDEX "is_active, blocked_at"
    }
```

## Database Tables

### 1. User (Django Built-in)

**Table Name:** `auth_user`

**Description:** Django's built-in user authentication model. Stores user account information.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `username` | VARCHAR(150) | UNIQUE, NOT NULL | Username for login |
| `email` | VARCHAR(254) | UNIQUE, NOT NULL | User email address |
| `password` | VARCHAR(128) | NOT NULL | Hashed password |
| `first_name` | VARCHAR(150) | NULLABLE | User's first name |
| `last_name` | VARCHAR(150) | NULLABLE | User's last name |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT=True | Account active status |
| `is_staff` | BOOLEAN | NOT NULL, DEFAULT=False | Staff access |
| `is_superuser` | BOOLEAN | NOT NULL, DEFAULT=False | Admin access |
| `date_joined` | TIMESTAMP | NOT NULL | Account creation date |
| `last_login` | TIMESTAMP | NULLABLE | Last login timestamp |

**Indexes:**
- Primary Key: `id`
- Unique Index: `username`
- Unique Index: `email`

**Design Decisions:**
- Uses Django's built-in User model for authentication
- Leverages existing security features and password hashing
- Standard Django fields provide flexibility for future extensions

---

### 2. UserProfile

**Table Name:** `users_userprofile`

**Description:** Extended user profile information. One-to-one relationship with User.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `user_id` | BIGINT | FOREIGN KEY, UNIQUE, NOT NULL | Reference to `auth_user.id` |
| `bio` | TEXT | NULLABLE | User biography |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE | Profile creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE | Last update timestamp |

**Relationships:**
- **One-to-One** with `User` via `user_id`
  - `ON DELETE CASCADE`: If user is deleted, profile is deleted

**Indexes:**
- Primary Key: `id`
- Unique Index: `user_id` (enforces one-to-one relationship)

**Design Decisions:**
- Separate table for profile data keeps User model clean
- One-to-one relationship ensures one profile per user
- CASCADE delete maintains referential integrity
- Timestamps track profile lifecycle

---

### 3. Poll

**Table Name:** `polls_poll`

**Description:** Represents a voting poll with title, description, scheduling, settings, security rules, and cached vote counts.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `title` | VARCHAR(200) | NOT NULL | Poll title |
| `description` | TEXT | NULLABLE | Poll description |
| `created_by_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `auth_user.id` |
| `category_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `polls_category.id` |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE, INDEXED | Creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE | Last update timestamp |
| `starts_at` | TIMESTAMP | NOT NULL | Poll start date/time |
| `ends_at` | TIMESTAMP | NULLABLE | Poll end date/time (null = no end) |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT=True | Active status flag |
| `is_draft` | BOOLEAN | NOT NULL, DEFAULT=False | Draft status (not visible publicly) |
| `settings` | JSONB | DEFAULT={} | Poll settings (allow_multiple_votes, show_results, etc.) |
| `security_rules` | JSONB | DEFAULT={} | Security rules (allowed_countries, blocked_countries, etc.) |
| `cached_total_votes` | INTEGER | DEFAULT=0 | Cached total vote count |
| `cached_unique_voters` | INTEGER | DEFAULT=0 | Cached unique voter count |

**Relationships:**
- **Many-to-One** with `User` via `created_by_id`
  - `ON DELETE CASCADE`: If creator is deleted, poll is deleted
- **Many-to-One** with `Category` via `category_id`
  - `ON DELETE SET NULL`: If category is deleted, poll category is set to NULL
- **Many-to-Many** with `Tag` (poll has many tags)
- **One-to-Many** with `PollOption` (poll has many options)
- **One-to-Many** with `Vote` (poll receives many votes)
- **One-to-Many** with `VoteAttempt` (poll receives many vote attempts)
- **One-to-One** with `PollAnalytics` (poll has one analytics record)
- **One-to-Many** with `Notification` (poll triggers notifications)
- **One-to-Many** with `FraudAlert` (poll has fraud alerts)

**Indexes:**
- Primary Key: `id`
- Index: `created_at` (for ordering: `-created_at`)
- Composite Index: `(is_active, starts_at, ends_at)` (for filtering active polls)
- Composite Index: `(is_draft, created_by_id)` (for draft visibility)
- Index: `category_id` (for category filtering)
- Foreign Key Indexes: `created_by_id`, `category_id`

**Design Decisions:**
- `starts_at` and `ends_at` allow scheduled polls
- `ends_at` is nullable to support open-ended polls
- `is_active` flag allows soft-deletion without data loss
- `is_draft` flag allows creating polls without publishing them
- `settings` JSONB field provides flexible poll configuration
- `security_rules` JSONB field stores geographic restrictions and security settings
- `cached_total_votes` and `cached_unique_voters` denormalize vote counts for performance
- CASCADE delete ensures data consistency when creator is removed
- Default ordering by `-created_at` for newest-first display

---

### 4. PollOption (formerly Choice)

**Table Name:** `polls_polloption`

**Description:** Represents a voting option within a poll with order and cached vote count.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `poll_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `polls_poll.id` |
| `text` | VARCHAR(200) | NOT NULL | Option text |
| `order` | INTEGER | DEFAULT=0 | Display order for options |
| `cached_vote_count` | INTEGER | DEFAULT=0 | Cached vote count for performance |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE | Creation timestamp |

**Relationships:**
- **Many-to-One** with `Poll` via `poll_id`
  - `ON DELETE CASCADE`: If poll is deleted, all options are deleted
- **One-to-Many** with `Vote` (option receives many votes)
- **One-to-Many** with `VoteAttempt` (option is target of vote attempts)

**Indexes:**
- Primary Key: `id`
- Foreign Key Index: `poll_id`
- Composite Index: `(poll_id, order)` (for ordering options within poll)

**Design Decisions:**
- Simple text field for option text (flexible for various poll types)
- `order` field allows custom ordering of options
- `cached_vote_count` denormalizes vote count for performance
- CASCADE delete ensures options are removed with poll
- Ordered by `order, id` to maintain display order
- No unique constraint on text - allows duplicate options if needed
- **Note:** `Choice` is a backward compatibility alias for `PollOption`

---

### 5. Vote

**Table Name:** `votes_vote`

**Description:** Represents a vote on a poll option with idempotency, fraud detection, and tracking fields. Supports both authenticated and anonymous voting.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `user_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `auth_user.id` (null for anonymous) |
| `option_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `polls_polloption.id` |
| `poll_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `polls_poll.id` |
| `voter_token` | VARCHAR(64) | INDEXED | Token for anonymous/guest voting |
| `idempotency_key` | VARCHAR(64) | UNIQUE, INDEXED | Idempotency key for duplicate prevention |
| `ip_address` | INET | INDEXED, NULLABLE | IP address of voter |
| `user_agent` | TEXT | NULLABLE | User agent string |
| `fingerprint` | VARCHAR(128) | INDEXED | Browser/device fingerprint |
| `is_valid` | BOOLEAN | DEFAULT=True, INDEXED | Whether vote is valid (False if fraud detected) |
| `fraud_reasons` | TEXT | NULLABLE | Comma-separated fraud detection reasons |
| `risk_score` | INTEGER | DEFAULT=0 | Risk score (0-100) from fraud detection |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE, INDEXED | Vote timestamp |

**Relationships:**
- **Many-to-One** with `User` via `user_id`
  - `ON DELETE CASCADE`: If user is deleted, votes are deleted
  - `NULLABLE`: Supports anonymous voting
- **Many-to-One** with `PollOption` via `option_id`
  - `ON DELETE CASCADE`: If option is deleted, votes are deleted
- **Many-to-One** with `Poll` via `poll_id`
  - `ON DELETE CASCADE`: If poll is deleted, votes are deleted
- **One-to-Many** with `FraudAlert` (vote can trigger fraud alerts)
- **One-to-Many** with `Notification` (vote can trigger notifications)

**Constraints:**
- **UNIQUE:** `idempotency_key` - Prevents duplicate votes from retries
- **UNIQUE:** `(user_id, poll_id)` WHERE `user_id IS NOT NULL` - Ensures one vote per authenticated user per poll
- **Note:** Anonymous votes are uniquely identified by `idempotency_key` and `voter_token`

**Indexes:**
- Primary Key: `id`
- Unique Index: `idempotency_key` (for fast idempotency checks)
- Composite Index: `(poll_id, voter_token)` (for poll + voter lookups)
- Composite Index: `(user_id, poll_id)` (for user poll lookups, unique constraint)
- Composite Index: `(poll_id, created_at)` (for poll vote history)
- Composite Index: `(ip_address, created_at)` (for IP + timestamp queries)
- Composite Index: `(fingerprint, created_at)` (for fingerprint tracking)
- Composite Index: `(is_valid, poll_id)` (for filtering valid votes)
- Foreign Key Indexes: `user_id`, `option_id`, `poll_id`

**Design Decisions:**
- **Idempotency Key:** Prevents duplicate votes from network retries or client errors
- **Nullable user_id:** Supports anonymous voting with `voter_token` and `fingerprint`
- **Unique Constraint (user, poll):** Enforces business rule: one vote per authenticated user per poll
- **Redundant poll_id:** Stored for performance (avoids JOIN to get poll from option)
- **Tracking Fields:** `ip_address`, `user_agent`, `fingerprint` enable fraud detection
- **Fraud Detection:** `is_valid`, `fraud_reasons`, `risk_score` track suspicious activity
- **Composite Indexes:** Optimize common query patterns (poll history, user lookups, fraud analysis)
- All foreign keys use CASCADE delete for data consistency

---

### 6. Category

**Table Name:** `polls_category`

**Description:** Represents a poll category (e.g., Politics, Sports, Technology).

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `name` | VARCHAR(100) | UNIQUE, NOT NULL | Category name |
| `slug` | VARCHAR(100) | UNIQUE, NOT NULL, INDEXED | URL-friendly slug |
| `description` | TEXT | NULLABLE | Category description |
| `created_at` | TIMESTAMP | NOT NULL | Creation timestamp |

**Relationships:**
- **One-to-Many** with `Poll` (category has many polls)
  - `ON DELETE SET NULL`: If category is deleted, poll category is set to NULL

**Indexes:**
- Primary Key: `id`
- Unique Index: `name`
- Unique Index: `slug`
- Index: `slug` (for filtering by slug)

---

### 7. Tag

**Table Name:** `polls_tag`

**Description:** Represents a freeform tag for polls (many-to-many relationship).

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `name` | VARCHAR(50) | UNIQUE, NOT NULL | Tag name |
| `slug` | VARCHAR(50) | UNIQUE, NOT NULL, INDEXED | URL-friendly slug |
| `created_at` | TIMESTAMP | NOT NULL | Creation timestamp |

**Relationships:**
- **Many-to-Many** with `Poll` (tag can be associated with many polls)

**Indexes:**
- Primary Key: `id`
- Unique Index: `name`
- Unique Index: `slug`
- Index: `name` (for searching)

---

### 8. VoteAttempt

**Table Name:** `votes_voteattempt`

**Description:** Immutable audit log of ALL vote attempts (success/failure). Tracks every attempt to vote, regardless of outcome.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `user_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `auth_user.id` |
| `poll_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `polls_poll.id` |
| `option_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `polls_polloption.id` |
| `voter_token` | VARCHAR(64) | INDEXED | Token for anonymous voting |
| `idempotency_key` | VARCHAR(64) | INDEXED | Idempotency key used in attempt |
| `ip_address` | INET | INDEXED, NULLABLE | IP address of attempt |
| `user_agent` | TEXT | NULLABLE | User agent string |
| `fingerprint` | VARCHAR(128) | INDEXED | Browser/device fingerprint |
| `success` | BOOLEAN | NOT NULL, DEFAULT=False | Whether attempt was successful |
| `error_message` | TEXT | NULLABLE | Error message if attempt failed |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE | Attempt timestamp |

**Relationships:**
- **Many-to-One** with `User` via `user_id`
  - `ON DELETE SET NULL`: If user is deleted, attempt record is kept
- **Many-to-One** with `Poll` via `poll_id`
  - `ON DELETE CASCADE`: If poll is deleted, attempts are deleted
- **Many-to-One** with `PollOption` via `option_id`
  - `ON DELETE SET NULL`: If option is deleted, attempt record is kept

**Indexes:**
- Primary Key: `id`
- Index: `poll_id, voter_token` (for poll + voter lookups)
- Index: `idempotency_key` (for idempotency tracking)
- Index: `ip_address, created_at` (for IP analysis)
- Index: `success, created_at` (for success/failure analysis)
- Index: `poll_id, created_at` (for poll attempt history)
- Foreign Key Indexes: `user_id`, `poll_id`, `option_id`

**Design Decisions:**
- **Immutable Audit Log:** Never updated, only created
- **Tracks All Attempts:** Both successful and failed attempts are logged
- **Error Tracking:** `error_message` captures failure reasons
- **Analytics:** Enables analysis of voting patterns and failure rates
- **Security:** Helps identify suspicious activity patterns

---

### 9. Follow

**Table Name:** `users_follow`

**Description:** Represents a follow relationship between users (social feature).

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `follower_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `auth_user.id` (user who follows) |
| `following_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `auth_user.id` (user being followed) |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE, INDEXED | Follow timestamp |

**Relationships:**
- **Many-to-One** with `User` via `follower_id`
  - `ON DELETE CASCADE`: If follower is deleted, follow is deleted
- **Many-to-One** with `User` via `following_id`
  - `ON DELETE CASCADE`: If following user is deleted, follow is deleted

**Constraints:**
- **UNIQUE:** `(follower_id, following_id)` - Prevents duplicate follows
- **CHECK:** `follower_id != following_id` - Users cannot follow themselves (application-level)

**Indexes:**
- Primary Key: `id`
- Unique Index: `(follower_id, following_id)` (for unique constraint)
- Composite Index: `(follower_id, created_at)` (for user's following list)
- Composite Index: `(following_id, created_at)` (for user's followers list)
- Foreign Key Indexes: `follower_id`, `following_id`

**Design Decisions:**
- **Bidirectional Relationship:** Uses two foreign keys to same table
- **Unique Constraint:** Prevents duplicate follows
- **Self-Reference Prevention:** Application validates users cannot follow themselves
- **Composite Indexes:** Optimize queries for "who I follow" and "who follows me"

---

### 10. PollAnalytics

**Table Name:** `analytics_pollanalytics`

**Description:** Pre-computed analytics data for polls. Denormalized for performance.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `poll_id` | BIGINT | FOREIGN KEY, UNIQUE, NOT NULL | Reference to `polls_poll.id` |
| `total_votes` | INTEGER | NOT NULL, DEFAULT=0 | Total vote count |
| `unique_voters` | INTEGER | NOT NULL, DEFAULT=0 | Number of unique voters |
| `last_updated` | TIMESTAMP | NOT NULL, AUTO_UPDATE | Last update timestamp |

**Relationships:**
- **One-to-One** with `Poll` via `poll_id`
  - `ON DELETE CASCADE`: If poll is deleted, analytics are deleted

**Indexes:**
- Primary Key: `id`
- Unique Index: `poll_id` (enforces one-to-one relationship)

**Design Decisions:**
- **Denormalized Design:** Stores pre-computed values for fast reads
- **One-to-One Relationship:** Each poll has exactly one analytics record
- **Default Values:** Initialize with 0 to avoid NULL issues
- **Auto-update Timestamp:** Tracks when analytics were last recalculated
- **Performance:** Avoids expensive COUNT queries on Vote table

---

## Relationships Summary

| Relationship | Type | Tables | Foreign Key | Delete Behavior |
|-------------|------|--------|-------------|----------------|
| User → UserProfile | One-to-One | `auth_user` → `users_userprofile` | `user_id` | CASCADE |
| User → NotificationPreference | One-to-One | `auth_user` → `notifications_notificationpreference` | `user_id` | CASCADE |
| User → Poll | One-to-Many | `auth_user` → `polls_poll` | `created_by_id` | CASCADE |
| User → Vote | One-to-Many | `auth_user` → `votes_vote` | `user_id` | CASCADE |
| User → VoteAttempt | One-to-Many | `auth_user` → `votes_voteattempt` | `user_id` | SET NULL |
| User → Follow (follower) | One-to-Many | `auth_user` → `users_follow` | `follower_id` | CASCADE |
| User → Follow (following) | One-to-Many | `auth_user` → `users_follow` | `following_id` | CASCADE |
| User → Notification | One-to-Many | `auth_user` → `notifications_notification` | `user_id` | CASCADE |
| User → AuditLog | One-to-Many | `auth_user` → `analytics_auditlog` | `user_id` | SET NULL |
| User → FraudAlert | One-to-Many | `auth_user` → `analytics_fraudalert` | `user_id` | SET NULL |
| Poll → Category | Many-to-One | `polls_poll` → `polls_category` | `category_id` | SET NULL |
| Poll → Tag | Many-to-Many | `polls_poll` ↔ `polls_tag` | (via `polls_poll_tags`) | - |
| Poll → PollOption | One-to-Many | `polls_poll` → `polls_polloption` | `poll_id` | CASCADE |
| Poll → Vote | One-to-Many | `polls_poll` → `votes_vote` | `poll_id` | CASCADE |
| Poll → VoteAttempt | One-to-Many | `polls_poll` → `votes_voteattempt` | `poll_id` | CASCADE |
| Poll → PollAnalytics | One-to-One | `polls_poll` → `analytics_pollanalytics` | `poll_id` | CASCADE |
| Poll → Notification | One-to-Many | `polls_poll` → `notifications_notification` | `poll_id` | CASCADE |
| Poll → FraudAlert | One-to-Many | `polls_poll` → `analytics_fraudalert` | `poll_id` | CASCADE |
| PollOption → Vote | One-to-Many | `polls_polloption` → `votes_vote` | `option_id` | CASCADE |
| PollOption → VoteAttempt | One-to-Many | `polls_polloption` → `votes_voteattempt` | `option_id` | SET NULL |
| Vote → FraudAlert | One-to-Many | `votes_vote` → `analytics_fraudalert` | `vote_id` | CASCADE |
| Vote → Notification | One-to-Many | `votes_vote` → `notifications_notification` | `vote_id` | CASCADE |
| Notification → NotificationDelivery | One-to-Many | `notifications_notification` → `notifications_notificationdelivery` | `notification_id` | CASCADE |

## Constraints Summary

### Primary Keys
- All tables use `id` (BIGINT, AUTO_INCREMENT) as primary key

### Unique Constraints
- `auth_user.username` - Username must be unique
- `auth_user.email` - Email must be unique
- `users_userprofile.user_id` - One profile per user
- `users_follow(follower_id, following_id)` - One follow relationship per pair (composite unique)
- `polls_category.name` - Category name must be unique
- `polls_category.slug` - Category slug must be unique
- `polls_tag.name` - Tag name must be unique
- `polls_tag.slug` - Tag slug must be unique
- `votes_vote.idempotency_key` - Idempotency key must be unique
- `votes_vote(user_id, poll_id)` WHERE `user_id IS NOT NULL` - One vote per authenticated user per poll (composite unique, conditional)
- `analytics_pollanalytics.poll_id` - One analytics record per poll
- `notifications_notificationpreference.user_id` - One preference record per user
- `notifications_notificationdelivery(notification_id, channel)` - One delivery record per channel per notification (composite unique)
- `analytics_ipreputation.ip_address` - One reputation record per IP
- `analytics_ipblock.ip_address` - One block record per IP
- `analytics_fingerprintblock.fingerprint` - One block record per fingerprint

### Foreign Key Constraints
- All foreign keys use `ON DELETE CASCADE` for referential integrity
- All foreign key columns are `NOT NULL` (except where explicitly nullable)

### Check Constraints
- `polls_poll.starts_at` should be <= `ends_at` (enforced at application level)
- `polls_poll.is_active` is boolean (enforced by data type)
- `analytics_pollanalytics.total_votes` >= 0 (enforced at application level)
- `analytics_pollanalytics.unique_voters` >= 0 (enforced at application level)

## Indexes Summary

### Primary Indexes
- All tables: `id` (PRIMARY KEY)

### Unique Indexes
- `auth_user.username`
- `auth_user.email`
- `users_userprofile.user_id`
- `votes_vote.idempotency_key`
- `votes_vote(user_id, poll_id)` (composite unique)
- `analytics_pollanalytics.poll_id`

### Performance Indexes
- `polls_poll.created_at` - For ordering polls by creation date
- `votes_vote(user_id, poll_id)` - For checking if user has voted (composite)
- `votes_vote(poll_id, created_at)` - For poll vote history and analytics queries
- `votes_vote.idempotency_key` - For fast idempotency checks

### Foreign Key Indexes
- All foreign key columns are automatically indexed by PostgreSQL

## Design Decisions and Rationale

### 1. Idempotency Key in Vote Table
**Decision:** Store `idempotency_key` as a unique, indexed field in the Vote table.

**Rationale:**
- Prevents duplicate votes from network retries or client-side errors
- Allows safe retry of failed requests
- Indexed for fast duplicate detection
- 64-character limit accommodates UUIDs and hashes

### 2. Redundant poll_id in Vote Table
**Decision:** Store `poll_id` directly in Vote, even though it can be derived from `choice_id`.

**Rationale:**
- **Performance:** Avoids JOIN operation when querying votes by poll
- **Data Integrity:** Enforces that choice belongs to poll (application-level validation)
- **Query Optimization:** Enables efficient composite indexes on `(poll_id, created_at)`
- **Minimal Storage Cost:** Small trade-off for significant performance gain

### 3. Unique Constraint: One Vote Per User Per Poll
**Decision:** Enforce `UNIQUE(user_id, poll_id)` constraint at database level.

**Rationale:**
- **Data Integrity:** Prevents duplicate votes at database level (defense in depth)
- **Performance:** Composite index supports fast existence checks
- **Business Rule:** Enforces core voting system requirement
- **Application Safety:** Database constraint prevents race conditions

### 4. Denormalized PollAnalytics Table
**Decision:** Store pre-computed analytics instead of calculating on-the-fly.

**Rationale:**
- **Performance:** Avoids expensive COUNT and GROUP BY queries
- **Scalability:** Analytics queries don't slow down as vote count grows
- **Real-time Updates:** Can be updated via Celery tasks or signals
- **Trade-off:** Requires maintaining consistency (acceptable for analytics)

### 5. CASCADE Delete on All Foreign Keys
**Decision:** Use `ON DELETE CASCADE` for all foreign key relationships.

**Rationale:**
- **Data Consistency:** Prevents orphaned records
- **Simplified Cleanup:** Deleting a poll automatically removes related data
- **Referential Integrity:** Database enforces relationships
- **Trade-off:** Cannot recover deleted data (acceptable for voting system)

### 6. Nullable ends_at in Poll Table
**Decision:** Allow `ends_at` to be NULL for open-ended polls.

**Rationale:**
- **Flexibility:** Supports both time-limited and open polls
- **Business Requirement:** Some polls may not have end dates
- **Application Logic:** `is_open` property handles NULL gracefully

### 7. is_active Flag Instead of Hard Delete
**Decision:** Use `is_active` boolean flag for soft deletion of polls.

**Rationale:**
- **Data Preservation:** Maintains historical data for analytics
- **Audit Trail:** Can track when polls were deactivated
- **Recovery:** Allows reactivation of polls if needed
- **Analytics:** Historical polls remain queryable

### 8. BigAutoField for Primary Keys
**Decision:** Use BIGINT (BigAutoField) for all primary keys.

**Rationale:**
- **Scalability:** Supports up to 9.2 quintillion records
- **Future-proof:** Prevents integer overflow in high-traffic systems
- **Consistency:** All tables use same primary key type
- **Minimal Overhead:** 8 bytes vs 4 bytes is negligible

### 9. Timestamp Fields with Auto-Update
**Decision:** Use `auto_now_add` and `auto_now` for timestamp fields.

**Rationale:**
- **Consistency:** Automatic timestamp management
- **Audit Trail:** Tracks creation and modification times
- **No Application Logic:** Database handles timestamps
- **Timezone Support:** Django handles timezone conversion

### 10. Composite Indexes for Common Queries
**Decision:** Create composite indexes on `(user_id, poll_id)` and `(poll_id, created_at)`.

**Rationale:**
- **Query Optimization:** Supports common query patterns
- **Unique Constraint:** Composite index enforces uniqueness
- **Sorting:** Index supports ORDER BY on `created_at`
- **Covering Index:** Can satisfy queries without table access

## Performance Considerations

### Query Optimization
1. **Vote Lookups:** Composite index `(user_id, poll_id)` optimizes "has user voted?" queries
2. **Poll History:** Index `(poll_id, created_at)` optimizes vote history queries
3. **Idempotency Checks:** Unique index on `idempotency_key` enables fast duplicate detection
4. **Analytics:** Denormalized `PollAnalytics` avoids expensive aggregations

### Scalability
1. **Partitioning:** Vote table could be partitioned by `poll_id` for very large polls
2. **Archiving:** Old polls could be archived to separate tables
3. **Caching:** PollAnalytics can be cached in Redis for frequently accessed polls
4. **Read Replicas:** Analytics queries could use read replicas

### Index Maintenance
- Indexes add write overhead but significantly improve read performance
- Composite indexes are most effective when queries match index column order
- Monitor index usage and remove unused indexes

## Data Integrity Rules

1. **One Vote Per User Per Poll:** Enforced by `UNIQUE(user_id, poll_id)` constraint
2. **Idempotency:** Enforced by `UNIQUE(idempotency_key)` constraint
3. **Referential Integrity:** All foreign keys use CASCADE delete
4. **Choice-Poll Consistency:** Application validates that choice belongs to poll
5. **Analytics Consistency:** Application maintains analytics via signals or tasks

## Future Considerations

### Potential Enhancements
1. **Vote History:** Track vote changes (if allowing vote updates)
2. **Poll Categories:** Add category/tag system for polls
3. **Vote Weighting:** Support weighted votes (e.g., ranked choice)
4. **Multi-Poll Voting:** Support voting on multiple polls in one transaction
5. **Audit Logging:** Separate audit table for vote history
6. **Soft Delete for Votes:** Track deleted votes for analytics
7. **Poll Templates:** Reusable poll templates
8. **Vote Anonymization:** Option to anonymize votes after poll closes

### Schema Evolution
- All changes should be made via Django migrations
- Consider backward compatibility for API consumers
- Use feature flags for gradual rollouts
- Monitor performance impact of schema changes

---

## ERD Diagram (Text Format)

```
┌─────────────────┐
│      User       │
│  (auth_user)    │
├─────────────────┤
│ PK id           │
│ UK username     │
│ UK email        │
│    password     │
│    ...          │
└────────┬────────┘
         │
         │ 1:1
         │
┌────────▼────────┐
│  UserProfile    │
├─────────────────┤
│ PK id           │
│ FK user_id (UK) │
│    bio          │
│    created_at   │
│    updated_at   │
└─────────────────┘

┌─────────────────┐
│      User       │
│  (auth_user)    │
└────────┬────────┘
         │
         │ 1:N
         │
┌────────▼────────┐      ┌──────────────┐
│      Poll       │ 1:N  │    Choice    │
├─────────────────┤◄─────┤              │
│ PK id           │      ├──────────────┤
│    title        │      │ PK id        │
│    description  │      │ FK poll_id   │
│ FK created_by_id│      │    text      │
│    starts_at    │      │    created_at│
│    ends_at      │      └──────┬───────┘
│    is_active    │             │
│    created_at   │             │ 1:N
│    updated_at   │             │
└────────┬────────┘             │
         │                      │
         │ 1:1                  │
         │                      │
┌────────▼────────┐      ┌──────▼───────┐
│ PollAnalytics   │      │     Vote     │
├─────────────────┤      ├──────────────┤
│ PK id           │      │ PK id        │
│ FK poll_id (UK) │      │ FK user_id   │
│    total_votes  │      │ FK choice_id │
│ unique_voters   │      │ FK poll_id   │
│    last_updated │      │ UK idempotency│
└─────────────────┘      │    created_at│
                         └──────────────┘
```

---

### 11. AuditLog

**Table Name:** `analytics_auditlog`

**Description:** Audit log for all API requests. Tracks every request for security, debugging, and analytics.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `user_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `auth_user.id` |
| `method` | VARCHAR(10) | NOT NULL | HTTP method (GET, POST, etc.) |
| `path` | VARCHAR(500) | NOT NULL | Request path |
| `query_params` | TEXT | NULLABLE | Query parameters as JSON string |
| `request_body` | TEXT | NULLABLE | Request body (truncated to 1000 chars) |
| `status_code` | INTEGER | NOT NULL | HTTP response status code |
| `ip_address` | INET | INDEXED, NULLABLE | Client IP address |
| `user_agent` | VARCHAR(500) | NULLABLE | User agent string |
| `request_id` | VARCHAR(64) | INDEXED | Request ID for tracing |
| `response_time` | FLOAT | NOT NULL | Response time in seconds |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE, INDEXED | Request timestamp |

**Relationships:**
- **Many-to-One** with `User` via `user_id`
  - `ON DELETE SET NULL`: If user is deleted, audit log is kept

**Indexes:**
- Primary Key: `id`
- Composite Index: `(user_id, created_at)` (for user activity)
- Composite Index: `(ip_address, created_at)` (for IP analysis)
- Index: `request_id` (for request tracing)
- Composite Index: `(method, path, created_at)` (for endpoint analysis)
- Foreign Key Index: `user_id`

**Design Decisions:**
- **Comprehensive Logging:** Tracks all API requests for security and debugging
- **Request Tracing:** `request_id` enables distributed tracing
- **Performance Monitoring:** `response_time` tracks API performance
- **Security Analysis:** IP and user agent tracking for fraud detection
- **Data Retention:** Consider archiving old logs for performance

---

### 12. Notification

**Table Name:** `notifications_notification`

**Description:** Represents a notification to a user (poll results, new polls, etc.).

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `user_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `auth_user.id` |
| `notification_type` | VARCHAR(50) | NOT NULL | Type of notification |
| `title` | VARCHAR(200) | NOT NULL | Notification title |
| `message` | TEXT | NOT NULL | Notification message |
| `poll_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `polls_poll.id` |
| `vote_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `votes_vote.id` |
| `metadata` | JSONB | DEFAULT={} | Additional metadata |
| `is_read` | BOOLEAN | DEFAULT=False, INDEXED | Whether user has read notification |
| `read_at` | TIMESTAMP | NULLABLE | When notification was read |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE, INDEXED | Creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE | Last update timestamp |

**Relationships:**
- **Many-to-One** with `User` via `user_id`
  - `ON DELETE CASCADE`: If user is deleted, notifications are deleted
- **Many-to-One** with `Poll` via `poll_id`
  - `ON DELETE CASCADE`: If poll is deleted, notifications are deleted
- **Many-to-One** with `Vote` via `vote_id`
  - `ON DELETE CASCADE`: If vote is deleted, notifications are deleted
- **One-to-Many** with `NotificationDelivery` (notification has multiple delivery records)

**Indexes:**
- Primary Key: `id`
- Composite Index: `(user_id, is_read, created_at)` (for user's unread notifications)
- Composite Index: `(notification_type, created_at)` (for type filtering)
- Composite Index: `(poll_id, created_at)` (for poll-related notifications)
- Foreign Key Indexes: `user_id`, `poll_id`, `vote_id`

**Notification Types:**
- `poll_results_available` - Poll results are available
- `new_poll_from_followed` - New poll from followed creator
- `poll_about_to_expire` - Poll about to expire
- `vote_flagged` - User's vote was flagged

---

### 13. NotificationPreference

**Table Name:** `notifications_notificationpreference`

**Description:** User preferences for notification types and delivery channels.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `user_id` | BIGINT | FOREIGN KEY, UNIQUE, NOT NULL | Reference to `auth_user.id` |
| `poll_results_available_email` | BOOLEAN | DEFAULT=True | Email for poll results |
| `poll_results_available_in_app` | BOOLEAN | DEFAULT=True | In-app for poll results |
| `poll_results_available_push` | BOOLEAN | DEFAULT=False | Push for poll results |
| `new_poll_from_followed_email` | BOOLEAN | DEFAULT=True | Email for new polls |
| `new_poll_from_followed_in_app` | BOOLEAN | DEFAULT=True | In-app for new polls |
| `new_poll_from_followed_push` | BOOLEAN | DEFAULT=False | Push for new polls |
| `poll_about_to_expire_email` | BOOLEAN | DEFAULT=True | Email for expiration warnings |
| `poll_about_to_expire_in_app` | BOOLEAN | DEFAULT=True | In-app for expiration warnings |
| `poll_about_to_expire_push` | BOOLEAN | DEFAULT=False | Push for expiration warnings |
| `vote_flagged_email` | BOOLEAN | DEFAULT=True | Email for flagged votes |
| `vote_flagged_in_app` | BOOLEAN | DEFAULT=True | In-app for flagged votes |
| `vote_flagged_push` | BOOLEAN | DEFAULT=False | Push for flagged votes |
| `email_enabled` | BOOLEAN | DEFAULT=True | Enable all email notifications |
| `in_app_enabled` | BOOLEAN | DEFAULT=True | Enable all in-app notifications |
| `push_enabled` | BOOLEAN | DEFAULT=False | Enable all push notifications |
| `unsubscribed` | BOOLEAN | DEFAULT=False | User has unsubscribed |
| `unsubscribed_at` | TIMESTAMP | NULLABLE | When user unsubscribed |
| `created_at` | TIMESTAMP | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL | Last update timestamp |

**Relationships:**
- **One-to-One** with `User` via `user_id`
  - `ON DELETE CASCADE`: If user is deleted, preferences are deleted

**Indexes:**
- Primary Key: `id`
- Unique Index: `user_id` (enforces one-to-one relationship)

---

### 14. NotificationDelivery

**Table Name:** `notifications_notificationdelivery`

**Description:** Tracks delivery status for each notification across different channels (email, in-app, push).

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `notification_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `notifications_notification.id` |
| `channel` | VARCHAR(20) | NOT NULL | Delivery channel (email, in_app, push) |
| `status` | VARCHAR(20) | DEFAULT='pending', INDEXED | Delivery status (pending, sent, failed, bounced) |
| `sent_at` | TIMESTAMP | NULLABLE | When notification was sent |
| `error_message` | TEXT | NULLABLE | Error message if delivery failed |
| `external_id` | VARCHAR(255) | NULLABLE | External ID from delivery service |
| `created_at` | TIMESTAMP | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL | Last update timestamp |

**Relationships:**
- **Many-to-One** with `Notification` via `notification_id`
  - `ON DELETE CASCADE`: If notification is deleted, deliveries are deleted

**Constraints:**
- **UNIQUE:** `(notification_id, channel)` - One delivery record per channel per notification

**Indexes:**
- Primary Key: `id`
- Unique Index: `(notification_id, channel)` (for unique constraint)
- Composite Index: `(status, created_at)` (for pending deliveries)
- Composite Index: `(channel, status)` (for channel-specific queries)
- Foreign Key Index: `notification_id`

---

### 15. FraudAlert

**Table Name:** `analytics_fraudalert`

**Description:** Fraud alerts for suspicious votes. Logs fraud detection events for investigation.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `vote_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `votes_vote.id` |
| `poll_id` | BIGINT | FOREIGN KEY, NOT NULL | Reference to `polls_poll.id` |
| `user_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `auth_user.id` |
| `ip_address` | INET | NULLABLE | IP address of suspicious vote |
| `reasons` | TEXT | NOT NULL | Comma-separated fraud detection reasons |
| `risk_score` | INTEGER | NOT NULL | Risk score (0-100) |
| `created_at` | TIMESTAMP | NOT NULL, AUTO_UPDATE, INDEXED | When fraud was detected |

**Relationships:**
- **Many-to-One** with `Vote` via `vote_id`
  - `ON DELETE CASCADE`: If vote is deleted, alert is deleted
- **Many-to-One** with `Poll` via `poll_id`
  - `ON DELETE CASCADE`: If poll is deleted, alerts are deleted
- **Many-to-One** with `User` via `user_id`
  - `ON DELETE SET NULL`: If user is deleted, alert is kept

**Indexes:**
- Primary Key: `id`
- Composite Index: `(poll_id, created_at)` (for poll fraud analysis)
- Composite Index: `(user_id, created_at)` (for user fraud analysis)
- Composite Index: `(ip_address, created_at)` (for IP fraud analysis)
- Composite Index: `(risk_score, created_at)` (for severity analysis)
- Foreign Key Indexes: `vote_id`, `poll_id`, `user_id`

---

### 16. IPReputation

**Table Name:** `analytics_ipreputation`

**Description:** IP reputation tracking for security and fraud prevention.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `ip_address` | INET | UNIQUE, INDEXED | IP address being tracked |
| `reputation_score` | INTEGER | DEFAULT=100 | Reputation score (0-100, higher is better) |
| `violation_count` | INTEGER | DEFAULT=0 | Number of violations |
| `successful_attempts` | INTEGER | DEFAULT=0 | Number of successful vote attempts |
| `failed_attempts` | INTEGER | DEFAULT=0 | Number of failed vote attempts |
| `first_seen` | TIMESTAMP | NOT NULL | When IP was first seen |
| `last_seen` | TIMESTAMP | NOT NULL | When IP was last seen |
| `last_violation_at` | TIMESTAMP | NULLABLE | When last violation occurred |

**Indexes:**
- Primary Key: `id`
- Unique Index: `ip_address`
- Composite Index: `(reputation_score, last_seen)` (for reputation queries)
- Composite Index: `(violation_count, last_seen)` (for violation analysis)

---

### 17. IPBlock

**Table Name:** `analytics_ipblock`

**Description:** Blocked IP addresses (automatic or manual blocking).

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `ip_address` | INET | UNIQUE, INDEXED | Blocked IP address |
| `reason` | TEXT | NOT NULL | Reason for blocking |
| `blocked_at` | TIMESTAMP | NOT NULL | When IP was blocked |
| `blocked_by_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `auth_user.id` (admin) |
| `is_active` | BOOLEAN | DEFAULT=True, INDEXED | Whether block is active |
| `is_manual` | BOOLEAN | DEFAULT=False | Whether block was manual |
| `auto_unblock_at` | TIMESTAMP | NULLABLE | When to auto-unblock |
| `unblocked_at` | TIMESTAMP | NULLABLE | When IP was unblocked |
| `unblocked_by_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `auth_user.id` (admin) |

**Indexes:**
- Primary Key: `id`
- Unique Index: `ip_address`
- Composite Index: `(ip_address, is_active)` (for active block checks)
- Composite Index: `(is_active, auto_unblock_at)` (for auto-unblock queries)
- Composite Index: `(is_manual, is_active)` (for manual block queries)

---

### 18. FingerprintBlock

**Table Name:** `analytics_fingerprintblock`

**Description:** Permanently blocked fingerprints due to suspicious activity.

| Column Name | Data Type | Constraints | Description |
|------------|-----------|-------------|-------------|
| `id` | BIGINT | PRIMARY KEY, AUTO_INCREMENT | Unique identifier |
| `fingerprint` | VARCHAR(128) | UNIQUE, INDEXED | Blocked fingerprint hash |
| `reason` | TEXT | NOT NULL | Reason for blocking |
| `blocked_at` | TIMESTAMP | NOT NULL | When fingerprint was blocked |
| `blocked_by_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `auth_user.id` (admin) |
| `is_active` | BOOLEAN | DEFAULT=True, INDEXED | Whether block is active |
| `unblocked_at` | TIMESTAMP | NULLABLE | When fingerprint was unblocked |
| `unblocked_by_id` | BIGINT | FOREIGN KEY, NULLABLE | Reference to `auth_user.id` (admin) |
| `first_seen_user_id` | BIGINT | FOREIGN KEY, NULLABLE | First user who used fingerprint |
| `total_users` | INTEGER | DEFAULT=0 | Total users who used fingerprint |
| `total_votes` | INTEGER | DEFAULT=0 | Total votes from fingerprint |

**Indexes:**
- Primary Key: `id`
- Unique Index: `fingerprint`
- Composite Index: `(fingerprint, is_active)` (for active block checks)
- Composite Index: `(is_active, blocked_at)` (for block analysis)

---

**Document Version:** 2.0  
**Last Updated:** 2025-11-22  
**Author:** Database Design Team

