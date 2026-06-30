# Database Schema Documentation

Detailed documentation for the Insurance Policy Agent database.

---

## Enum Types

### `policy_type`
| Value | Description |
|-------|-------------|
| `health` | Health / medical insurance |
| `auto` | Car / bike / vehicle insurance |
| `home` | Home / property insurance |
| `life` | Life / term insurance |
| `travel` | Travel insurance (domestic/international) |

### `policy_status`
| Value | Description |
|-------|-------------|
| `active` | Policy is currently in force |
| `expired` | Policy has passed its end date |
| `cancelled` | Policy was cancelled by customer or insurer |
| `pending` | Policy application is being processed |

### `claim_status`
| Value | Description |
|-------|-------------|
| `submitted` | Claim has been filed and is awaiting initial review |
| `under_review` | Claim is being investigated / documents verified |
| `approved` | Claim has been approved for payment |
| `denied` | Claim has been rejected |
| `paid` | Payment has been disbursed to the customer |
| `closed` | Claim is fully resolved and archived |

### `kb_category`
| Value | Description |
|-------|-------------|
| `claims_process` | How to file, track, and manage claims |
| `policy_management` | Renewing, updating, and cancelling policies |
| `billing_payments` | Premium payments, methods, and installments |
| `coverage_info` | What's covered, exclusions, and limits |
| `general_faq` | General questions about insurance |

---

## Table: `customers`

Customer master data.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique customer identifier |
| `first_name` | VARCHAR(100) | NOT NULL | Customer's first name |
| `last_name` | VARCHAR(100) | NOT NULL | Customer's last name |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | Email address |
| `phone` | VARCHAR(20) | — | Phone number (with country code) |
| `date_of_birth` | DATE | — | Date of birth |
| `address_line1` | VARCHAR(255) | — | Street address line 1 |
| `address_line2` | VARCHAR(255) | — | Street address line 2 |
| `city` | VARCHAR(100) | — | City |
| `state` | VARCHAR(100) | — | State |
| `pincode` | VARCHAR(10) | — | PIN code |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update timestamp (auto-updated) |

**Indexes:** `email`, `phone`

---

## Table: `policies`

Insurance policies linked to customers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique policy identifier |
| `policy_number` | VARCHAR(20) | UNIQUE, NOT NULL | Human-readable policy number (e.g., POL-HLT-2024-001) |
| `customer_id` | UUID | FK → customers.id, NOT NULL | Owning customer |
| `policy_type` | policy_type | NOT NULL | Type of insurance |
| `status` | policy_status | NOT NULL, DEFAULT 'active' | Current policy status |
| `premium_amount` | DECIMAL(12,2) | NOT NULL | Annual premium in INR |
| `coverage_amount` | DECIMAL(14,2) | NOT NULL | Sum insured / coverage limit in INR |
| `deductible` | DECIMAL(10,2) | DEFAULT 0 | Deductible amount in INR |
| `start_date` | DATE | NOT NULL | Policy start date |
| `end_date` | DATE | NOT NULL | Policy end date |
| `description` | TEXT | — | Policy description / details |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update timestamp (auto-updated) |

**Indexes:** `customer_id`, `policy_number`, `status`, `policy_type`  
**Foreign Key:** `customer_id` → `customers.id` (ON DELETE CASCADE)

---

## Table: `claims`

Insurance claims linked to policies.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique claim identifier |
| `claim_number` | VARCHAR(20) | UNIQUE, NOT NULL | Human-readable claim number (e.g., CLM-2024-0001) |
| `policy_id` | UUID | FK → policies.id, NOT NULL | Associated policy |
| `status` | claim_status | NOT NULL, DEFAULT 'submitted' | Current claim status |
| `claim_type` | VARCHAR(100) | NOT NULL | Type of claim (Hospitalization, Accident, Theft, etc.) |
| `claim_amount` | DECIMAL(12,2) | NOT NULL | Amount claimed in INR |
| `approved_amount` | DECIMAL(12,2) | — | Amount approved (NULL if pending) |
| `description` | TEXT | — | Details of the incident/claim |
| `incident_date` | DATE | NOT NULL | Date of the incident |
| `filed_date` | DATE | NOT NULL, DEFAULT CURRENT_DATE | Date claim was filed |
| `resolved_date` | DATE | — | Date claim was resolved (NULL if pending) |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update timestamp (auto-updated) |

**Indexes:** `policy_id`, `claim_number`, `status`, `filed_date`  
**Foreign Key:** `policy_id` → `policies.id` (ON DELETE CASCADE)

---

## Table: `claim_status_history`

Audit trail for claim status changes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique history entry ID |
| `claim_id` | UUID | FK → claims.id, NOT NULL | Associated claim |
| `old_status` | claim_status | — | Previous status (NULL for initial entry) |
| `new_status` | claim_status | NOT NULL | New status |
| `notes` | TEXT | — | Description of the status change |
| `changed_by` | VARCHAR(100) | DEFAULT 'system' | Who made the change (system/agent name) |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Timestamp of the change |

**Indexes:** `claim_id`  
**Foreign Key:** `claim_id` → `claims.id` (ON DELETE CASCADE)

---

## Table: `knowledge_base`

FAQ and knowledge articles for the agent.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique article ID |
| `category` | kb_category | NOT NULL | Article category |
| `question` | TEXT | NOT NULL | The question / article title |
| `answer` | TEXT | NOT NULL | The detailed answer |
| `tags` | TEXT[] | DEFAULT '{}' | Searchable tags array |
| `is_published` | BOOLEAN | DEFAULT TRUE | Whether the article is visible |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | Last update timestamp (auto-updated) |

**Indexes:** `category`, `tags` (GIN index for array search)

---

## Relationships

```
customers (1) ──── (N) policies
policies  (1) ──── (N) claims
claims    (1) ──── (N) claim_status_history
knowledge_base     (standalone)
```

All foreign keys use `ON DELETE CASCADE` — deleting a customer removes their policies, claims, and history.

---

## Example Agent Queries

### 1. Check claim status with full history

```sql
SELECT
    c.claim_number,
    c.status AS current_status,
    c.claim_type,
    c.claim_amount,
    c.approved_amount,
    c.description,
    c.incident_date,
    c.filed_date,
    c.resolved_date,
    p.policy_number,
    p.policy_type,
    cu.first_name || ' ' || cu.last_name AS customer_name
FROM claims c
JOIN policies p ON c.policy_id = p.id
JOIN customers cu ON p.customer_id = cu.id
WHERE c.claim_number = 'CLM-2024-0001';
```

### 2. Get claim status history (timeline)

```sql
SELECT
    new_status,
    old_status,
    notes,
    changed_by,
    created_at
FROM claim_status_history
WHERE claim_id = (SELECT id FROM claims WHERE claim_number = 'CLM-2024-0001')
ORDER BY created_at ASC;
```

### 3. Search knowledge base by keyword

```sql
SELECT question, answer, category, tags
FROM knowledge_base
WHERE is_published = true
  AND (
    question ILIKE '%claim%'
    OR answer ILIKE '%claim%'
    OR 'claim' = ANY(tags)
  )
ORDER BY category;
```

### 4. Get all active policies for a customer

```sql
SELECT
    p.policy_number,
    p.policy_type,
    p.status,
    p.premium_amount,
    p.coverage_amount,
    p.start_date,
    p.end_date,
    p.description
FROM policies p
JOIN customers cu ON p.customer_id = cu.id
WHERE cu.email = 'rajesh.sharma@email.com'
  AND p.status = 'active';
```

### 5. Get customer with all their claims

```sql
SELECT
    cu.first_name || ' ' || cu.last_name AS customer_name,
    cu.email,
    cu.phone,
    p.policy_number,
    c.claim_number,
    c.status,
    c.claim_type,
    c.claim_amount
FROM customers cu
JOIN policies p ON p.customer_id = cu.id
JOIN claims c ON c.policy_id = p.id
WHERE cu.id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
ORDER BY c.filed_date DESC;
```
