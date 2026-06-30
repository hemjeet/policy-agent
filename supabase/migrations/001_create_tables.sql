-- ============================================================
-- Insurance Policy Agent — Database Schema
-- Migration: 001_create_tables.sql
-- Description: Creates all tables, enums, indexes, and triggers
-- ============================================================

-- ===================
-- ENUM TYPES
-- ===================

-- Policy types
CREATE TYPE policy_type AS ENUM (
    'health',
    'auto',
    'home',
    'life',
    'travel'
);

-- Policy status
CREATE TYPE policy_status AS ENUM (
    'active',
    'expired',
    'cancelled',
    'pending'
);

-- Claim status
CREATE TYPE claim_status AS ENUM (
    'submitted',
    'under_review',
    'approved',
    'denied',
    'paid',
    'closed'
);

-- Knowledge base categories
CREATE TYPE kb_category AS ENUM (
    'claims_process',
    'policy_management',
    'billing_payments',
    'coverage_info',
    'general_faq'
);


-- ===================
-- TABLES
-- ===================

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    phone           VARCHAR(20),
    date_of_birth   DATE,
    address_line1   VARCHAR(255),
    address_line2   VARCHAR(255),
    city            VARCHAR(100),
    state           VARCHAR(100),
    pincode         VARCHAR(10),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Policies table
CREATE TABLE IF NOT EXISTS policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_number   VARCHAR(20) UNIQUE NOT NULL,
    customer_id     UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    policy_type     policy_type NOT NULL,
    status          policy_status NOT NULL DEFAULT 'active',
    premium_amount  DECIMAL(12, 2) NOT NULL,
    coverage_amount DECIMAL(14, 2) NOT NULL,
    deductible      DECIMAL(10, 2) DEFAULT 0,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Claims table
CREATE TABLE IF NOT EXISTS claims (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_number    VARCHAR(20) UNIQUE NOT NULL,
    policy_id       UUID NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    status          claim_status NOT NULL DEFAULT 'submitted',
    claim_type      VARCHAR(100) NOT NULL,
    claim_amount    DECIMAL(12, 2) NOT NULL,
    approved_amount DECIMAL(12, 2),
    description     TEXT,
    incident_date   DATE NOT NULL,
    filed_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    resolved_date   DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Claim status history (audit trail)
CREATE TABLE IF NOT EXISTS claim_status_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id        UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    old_status      claim_status,
    new_status      claim_status NOT NULL,
    notes           TEXT,
    changed_by      VARCHAR(100) DEFAULT 'system',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Knowledge base table
CREATE TABLE IF NOT EXISTS knowledge_base (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category        kb_category NOT NULL,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    tags            TEXT[] DEFAULT '{}',
    is_published    BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ===================
-- INDEXES
-- ===================

-- Customers
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_phone ON customers(phone);

-- Policies
CREATE INDEX idx_policies_customer_id ON policies(customer_id);
CREATE INDEX idx_policies_policy_number ON policies(policy_number);
CREATE INDEX idx_policies_status ON policies(status);
CREATE INDEX idx_policies_type ON policies(policy_type);

-- Claims
CREATE INDEX idx_claims_policy_id ON claims(policy_id);
CREATE INDEX idx_claims_claim_number ON claims(claim_number);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_claims_filed_date ON claims(filed_date);

-- Claim status history
CREATE INDEX idx_claim_history_claim_id ON claim_status_history(claim_id);

-- Knowledge base
CREATE INDEX idx_kb_category ON knowledge_base(category);
CREATE INDEX idx_kb_tags ON knowledge_base USING GIN(tags);


-- ===================
-- TRIGGERS (auto-update updated_at)
-- ===================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_policies_updated_at
    BEFORE UPDATE ON policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_claims_updated_at
    BEFORE UPDATE ON claims
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_kb_updated_at
    BEFORE UPDATE ON knowledge_base
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
