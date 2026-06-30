# Agent Tools Specification

This document defines the tool functions that the Insurance Policy Agent uses to query the Supabase database and serve user requests.

---

## Overview

The agent has access to 4 primary tools:

| Tool | Purpose | Input |
|------|---------|-------|
| `check_claim_status` | Look up claim details and status history | Claim number or policy number |
| `get_policy_info` | Retrieve policy details | Policy number or customer ID |
| `search_knowledge_base` | Search FAQ/knowledge articles | Query string, optional category |
| `get_customer_info` | Retrieve customer details | Customer ID, email, or phone |

---

## Tool 1: `check_claim_status`

### Description
Retrieves the current status and full history of an insurance claim. The agent uses this when a user asks about their claim status, claim details, or claim timeline.

### Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `claim_number` | string | No* | Claim number (e.g., "CLM-2024-0001") |
| `policy_number` | string | No* | Policy number to find all associated claims |

*At least one of `claim_number` or `policy_number` must be provided.

### Output Format

```json
{
  "claim": {
    "claim_number": "CLM-2024-0001",
    "status": "paid",
    "claim_type": "Hospitalization",
    "claim_amount": 85000.00,
    "approved_amount": 80000.00,
    "description": "Hospital admission for knee surgery...",
    "incident_date": "2024-05-10",
    "filed_date": "2024-05-15",
    "resolved_date": "2024-06-01",
    "policy_number": "POL-HLT-2024-001",
    "policy_type": "health",
    "customer_name": "Rajesh Sharma"
  },
  "history": [
    {
      "old_status": null,
      "new_status": "submitted",
      "notes": "Claim submitted by customer via portal.",
      "changed_by": "system",
      "timestamp": "2024-05-15T10:30:00Z"
    },
    {
      "old_status": "submitted",
      "new_status": "under_review",
      "notes": "Documents verified. Assigned to claims adjuster.",
      "changed_by": "agent_ravi",
      "timestamp": "2024-05-16T14:00:00Z"
    }
  ]
}
```

### SQL Query (Behind the Tool)

```sql
-- Get claim details
SELECT c.*, p.policy_number, p.policy_type,
       cu.first_name || ' ' || cu.last_name AS customer_name
FROM claims c
JOIN policies p ON c.policy_id = p.id
JOIN customers cu ON p.customer_id = cu.id
WHERE c.claim_number = $1;

-- Get claim history
SELECT old_status, new_status, notes, changed_by, created_at
FROM claim_status_history
WHERE claim_id = $1
ORDER BY created_at ASC;
```

### Example User Queries
- "What is the status of claim CLM-2024-0001?"
- "Show me the history of my claim"
- "Are there any pending claims on policy POL-HLT-2024-001?"

---

## Tool 2: `get_policy_info`

### Description
Retrieves detailed information about one or more insurance policies. Used when users ask about their coverage, premium, validity, or policy details.

### Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `policy_number` | string | No* | Specific policy number |
| `customer_id` | string | No* | Customer UUID to get all their policies |
| `customer_email` | string | No* | Customer email to look up policies |
| `status_filter` | string | No | Filter by status: "active", "expired", "cancelled", "pending" |

*At least one of `policy_number`, `customer_id`, or `customer_email` must be provided.

### Output Format

```json
{
  "policies": [
    {
      "policy_number": "POL-HLT-2024-001",
      "policy_type": "health",
      "status": "active",
      "premium_amount": 15000.00,
      "coverage_amount": 500000.00,
      "deductible": 5000.00,
      "start_date": "2024-01-01",
      "end_date": "2025-12-31",
      "description": "Family floater health insurance...",
      "customer_name": "Rajesh Sharma",
      "active_claims_count": 2
    }
  ]
}
```

### SQL Query (Behind the Tool)

```sql
SELECT p.*, cu.first_name || ' ' || cu.last_name AS customer_name,
       (SELECT COUNT(*) FROM claims c
        WHERE c.policy_id = p.id
        AND c.status NOT IN ('closed', 'denied', 'paid')) AS active_claims_count
FROM policies p
JOIN customers cu ON p.customer_id = cu.id
WHERE p.policy_number = $1;
```

### Example User Queries
- "Tell me about policy POL-HLT-2024-001"
- "What is my coverage amount?"
- "When does my auto insurance expire?"
- "Show me all active policies for rajesh.sharma@email.com"

---

## Tool 3: `search_knowledge_base`

### Description
Searches the knowledge base for relevant FAQ articles. Used when users ask general insurance questions, how-to questions, or need information about processes.

### Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query / question |
| `category` | string | No | Filter by category: "claims_process", "policy_management", "billing_payments", "coverage_info", "general_faq" |
| `limit` | integer | No | Max results to return (default: 3) |

### Output Format

```json
{
  "articles": [
    {
      "category": "claims_process",
      "question": "How do I file a new insurance claim?",
      "answer": "To file a new insurance claim, follow these steps...",
      "tags": ["claim", "file", "new", "submit", "how to"],
      "relevance_score": 0.95
    }
  ],
  "total_found": 3
}
```

### SQL Query (Behind the Tool)

```sql
SELECT category, question, answer, tags
FROM knowledge_base
WHERE is_published = true
  AND (
    question ILIKE '%' || $1 || '%'
    OR answer ILIKE '%' || $1 || '%'
    OR $1 = ANY(tags)
  )
ORDER BY
  CASE WHEN $1 = ANY(tags) THEN 0 ELSE 1 END,
  CASE WHEN question ILIKE '%' || $1 || '%' THEN 0 ELSE 1 END
LIMIT $2;
```

### Example User Queries
- "How do I file a claim?"
- "What documents do I need for a health claim?"
- "Is my premium tax deductible?"
- "What is not covered under health insurance?"

---

## Tool 4: `get_customer_info`

### Description
Retrieves customer profile information. Used to identify customers and pull their associated data.

### Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `customer_id` | string | No* | Customer UUID |
| `email` | string | No* | Customer email address |
| `phone` | string | No* | Customer phone number |

*At least one parameter must be provided.

### Output Format

```json
{
  "customer": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Rajesh Sharma",
    "email": "rajesh.sharma@email.com",
    "phone": "+91-9876543210",
    "date_of_birth": "1985-03-15",
    "address": "42, MG Road, Sector 5, Mumbai, Maharashtra - 400001",
    "total_policies": 2,
    "active_policies": 2,
    "total_claims": 3,
    "pending_claims": 1
  }
}
```

### SQL Query (Behind the Tool)

```sql
SELECT cu.*,
       (SELECT COUNT(*) FROM policies p WHERE p.customer_id = cu.id) AS total_policies,
       (SELECT COUNT(*) FROM policies p WHERE p.customer_id = cu.id AND p.status = 'active') AS active_policies,
       (SELECT COUNT(*) FROM claims c JOIN policies p ON c.policy_id = p.id WHERE p.customer_id = cu.id) AS total_claims,
       (SELECT COUNT(*) FROM claims c JOIN policies p ON c.policy_id = p.id WHERE p.customer_id = cu.id AND c.status IN ('submitted', 'under_review')) AS pending_claims
FROM customers cu
WHERE cu.email = $1;
```

### Example User Queries
- "Look up customer rajesh.sharma@email.com"
- "What's the profile for customer ID a1b2c3d4...?"
- "Find customer with phone +91-9876543210"

---

## Agent System Prompt (Suggested)

```
You are an Insurance Policy Agent assistant. You help customers with:
1. Checking claim status and history
2. Viewing policy information and coverage details
3. Answering general insurance questions from the knowledge base
4. Looking up customer information

Guidelines:
- Always be polite and professional
- When a customer asks about claims, use check_claim_status
- When asked about policies, use get_policy_info
- For general questions, search the knowledge_base first
- If the customer provides an email or phone, use get_customer_info to identify them
- Present amounts in INR format (e.g., ₹85,000)
- Include relevant dates in DD-MMM-YYYY format
- If a claim is denied, explain the reason and suggest next steps
- Never expose internal IDs (UUIDs) to customers
```

---

## Error Handling

All tools should handle these error cases:

| Error | Response |
|-------|----------|
| No results found | "I couldn't find any records matching that. Could you please verify the claim/policy number?" |
| Invalid input format | "That doesn't look like a valid claim number. Claim numbers follow the format CLM-YYYY-NNNN." |
| Database error | "I'm experiencing technical difficulties. Please try again or contact support at 1800-XXX-XXXX." |
| Multiple matches | Return all matches and ask the customer to clarify which one |
