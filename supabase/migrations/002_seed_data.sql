-- ============================================================
-- Insurance Policy Agent — Sample Seed Data
-- Migration: 002_seed_data.sql
-- Description: Inserts realistic sample data for testing
-- ============================================================


-- ===================
-- CUSTOMERS (5 sample customers)
-- ===================

INSERT INTO customers (id, first_name, last_name, email, phone, date_of_birth, address_line1, address_line2, city, state, pincode)
VALUES
    ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'Rajesh', 'Sharma', 'rajesh.sharma@email.com', '+91-9876543210', '1985-03-15', '42, MG Road', 'Sector 5', 'Mumbai', 'Maharashtra', '400001'),
    ('b2c3d4e5-f6a7-8901-bcde-f12345678901', 'Priya', 'Patel', 'priya.patel@email.com', '+91-9876543211', '1990-07-22', '18, Nehru Nagar', NULL, 'Ahmedabad', 'Gujarat', '380001'),
    ('c3d4e5f6-a7b8-9012-cdef-123456789012', 'Amit', 'Kumar', 'amit.kumar@email.com', '+91-9876543212', '1978-11-30', '7, Civil Lines', 'Near Railway Station', 'Delhi', 'Delhi', '110001'),
    ('d4e5f6a7-b8c9-0123-defa-234567890123', 'Sneha', 'Reddy', 'sneha.reddy@email.com', '+91-9876543213', '1992-01-10', '23, Jubilee Hills', NULL, 'Hyderabad', 'Telangana', '500033'),
    ('e5f6a7b8-c9d0-1234-efab-345678901234', 'Vikram', 'Singh', 'vikram.singh@email.com', '+91-9876543214', '1982-06-05', '15, Aashiana Colony', 'Gomti Nagar', 'Lucknow', 'Uttar Pradesh', '226010');


-- ===================
-- POLICIES (8 policies across different types)
-- ===================

INSERT INTO policies (id, policy_number, customer_id, policy_type, status, premium_amount, coverage_amount, deductible, start_date, end_date, description)
VALUES
    -- Rajesh Sharma's policies
    ('11111111-1111-1111-1111-111111111111', 'POL-HLT-2024-001', 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'health', 'active', 15000.00, 500000.00, 5000.00, '2024-01-01', '2025-12-31', 'Family floater health insurance - covers self, spouse, and 2 children'),
    ('22222222-2222-2222-2222-222222222222', 'POL-AUT-2024-002', 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'auto', 'active', 8500.00, 300000.00, 2000.00, '2024-03-15', '2025-03-14', 'Comprehensive car insurance - Maruti Swift Dzire 2022'),

    -- Priya Patel's policies
    ('33333333-3333-3333-3333-333333333333', 'POL-HLT-2024-003', 'b2c3d4e5-f6a7-8901-bcde-f12345678901', 'health', 'active', 12000.00, 300000.00, 3000.00, '2024-02-01', '2025-01-31', 'Individual health insurance with maternity cover'),
    ('44444444-4444-4444-4444-444444444444', 'POL-TRV-2024-004', 'b2c3d4e5-f6a7-8901-bcde-f12345678901', 'travel', 'expired', 2500.00, 1000000.00, 0.00, '2024-06-01', '2024-06-30', 'International travel insurance - Europe trip'),

    -- Amit Kumar's policies
    ('55555555-5555-5555-5555-555555555555', 'POL-HOM-2024-005', 'c3d4e5f6-a7b8-9012-cdef-123456789012', 'home', 'active', 6000.00, 2000000.00, 10000.00, '2024-01-15', '2025-01-14', 'Home insurance - 3BHK flat in Civil Lines, Delhi'),
    ('66666666-6666-6666-6666-666666666666', 'POL-LIF-2024-006', 'c3d4e5f6-a7b8-9012-cdef-123456789012', 'life', 'active', 25000.00, 5000000.00, 0.00, '2024-04-01', '2044-03-31', 'Term life insurance - 20 year plan'),

    -- Sneha Reddy's policy
    ('77777777-7777-7777-7777-777777777777', 'POL-HLT-2024-007', 'd4e5f6a7-b8c9-0123-defa-234567890123', 'health', 'active', 18000.00, 1000000.00, 5000.00, '2024-05-01', '2025-04-30', 'Super top-up health insurance plan'),

    -- Vikram Singh's policy
    ('88888888-8888-8888-8888-888888888888', 'POL-AUT-2024-008', 'e5f6a7b8-c9d0-1234-efab-345678901234', 'auto', 'cancelled', 12000.00, 500000.00, 3000.00, '2024-01-01', '2024-12-31', 'Comprehensive bike insurance - Royal Enfield Classic 350');


-- ===================
-- CLAIMS (10 claims in various statuses)
-- ===================

INSERT INTO claims (id, claim_number, policy_id, status, claim_type, claim_amount, approved_amount, description, incident_date, filed_date, resolved_date)
VALUES
    -- Rajesh's health claim (paid)
    ('aaaa1111-1111-1111-1111-111111111111', 'CLM-2024-0001', '11111111-1111-1111-1111-111111111111', 'paid', 'Hospitalization', 85000.00, 80000.00, 'Hospital admission for knee surgery at Lilavati Hospital, Mumbai. 3-day stay.', '2024-05-10', '2024-05-15', '2024-06-01'),

    -- Rajesh's auto claim (under review)
    ('aaaa2222-2222-2222-2222-222222222222', 'CLM-2024-0002', '22222222-2222-2222-2222-222222222222', 'under_review', 'Accident Damage', 45000.00, NULL, 'Minor fender bender at Andheri signal. Front bumper and headlight damage.', '2024-08-20', '2024-08-22', NULL),

    -- Priya's health claim (approved)
    ('aaaa3333-3333-3333-3333-333333333333', 'CLM-2024-0003', '33333333-3333-3333-3333-333333333333', 'approved', 'OPD Treatment', 12000.00, 10000.00, 'Dental treatment - root canal procedure at Apollo Dental Clinic.', '2024-07-05', '2024-07-08', '2024-07-25'),

    -- Priya's travel claim (denied)
    ('aaaa4444-4444-4444-4444-444444444444', 'CLM-2024-0004', '44444444-4444-4444-4444-444444444444', 'denied', 'Flight Delay', 15000.00, 0.00, 'Flight delayed by 3 hours at Frankfurt airport. Claim for hotel and food expenses.', '2024-06-15', '2024-06-20', '2024-07-10'),

    -- Amit's home claim (submitted)
    ('aaaa5555-5555-5555-5555-555555555555', 'CLM-2024-0005', '55555555-5555-5555-5555-555555555555', 'submitted', 'Water Damage', 75000.00, NULL, 'Water pipe burst in kitchen causing damage to flooring and cabinets.', '2024-09-01', '2024-09-03', NULL),

    -- Amit's home claim (closed)
    ('aaaa6666-6666-6666-6666-666666666666', 'CLM-2024-0006', '55555555-5555-5555-5555-555555555555', 'closed', 'Theft', 150000.00, 120000.00, 'Burglary - laptop, jewelry, and electronics stolen. FIR filed.', '2024-03-10', '2024-03-12', '2024-04-20'),

    -- Sneha's health claim (under review)
    ('aaaa7777-7777-7777-7777-777777777777', 'CLM-2024-0007', '77777777-7777-7777-7777-777777777777', 'under_review', 'Hospitalization', 200000.00, NULL, 'Emergency appendectomy at KIMS Hospital, Hyderabad. 5-day stay in private room.', '2024-09-15', '2024-09-17', NULL),

    -- Sneha's health claim (submitted)
    ('aaaa8888-8888-8888-8888-888888888888', 'CLM-2024-0008', '77777777-7777-7777-7777-777777777777', 'submitted', 'Diagnostic Tests', 25000.00, NULL, 'Annual health checkup with full body scan and blood work at Apollo Diagnostics.', '2024-10-01', '2024-10-03', NULL),

    -- Rajesh's health claim (submitted - recent)
    ('aaaa9999-9999-9999-9999-999999999999', 'CLM-2024-0009', '11111111-1111-1111-1111-111111111111', 'submitted', 'OPD Treatment', 8000.00, NULL, 'Physiotherapy sessions (10 sessions) for post-surgery knee rehabilitation.', '2024-09-20', '2024-09-25', NULL),

    -- Vikram's auto claim (denied - policy cancelled)
    ('aaaabbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'CLM-2024-0010', '88888888-8888-8888-8888-888888888888', 'denied', 'Accident Damage', 35000.00, 0.00, 'Bike scratched during parking. Claim denied as policy was cancelled before incident.', '2024-11-01', '2024-11-05', '2024-11-15');


-- ===================
-- CLAIM STATUS HISTORY (audit trail)
-- ===================

INSERT INTO claim_status_history (claim_id, old_status, new_status, notes, changed_by)
VALUES
    -- CLM-2024-0001 history (submitted → under_review → approved → paid)
    ('aaaa1111-1111-1111-1111-111111111111', NULL, 'submitted', 'Claim submitted by customer via portal.', 'system'),
    ('aaaa1111-1111-1111-1111-111111111111', 'submitted', 'under_review', 'Documents verified. Assigned to claims adjuster.', 'agent_ravi'),
    ('aaaa1111-1111-1111-1111-111111111111', 'under_review', 'approved', 'Claim approved. Rs 5,000 deductible applied.', 'manager_sunita'),
    ('aaaa1111-1111-1111-1111-111111111111', 'approved', 'paid', 'Payment of Rs 80,000 processed to bank account.', 'system'),

    -- CLM-2024-0002 history (submitted → under_review)
    ('aaaa2222-2222-2222-2222-222222222222', NULL, 'submitted', 'Claim filed online with photos of damage.', 'system'),
    ('aaaa2222-2222-2222-2222-222222222222', 'submitted', 'under_review', 'Surveyor assigned. Inspection scheduled for 2024-08-28.', 'agent_meera'),

    -- CLM-2024-0003 history (submitted → under_review → approved)
    ('aaaa3333-3333-3333-3333-333333333333', NULL, 'submitted', 'Claim submitted with dental bills.', 'system'),
    ('aaaa3333-3333-3333-3333-333333333333', 'submitted', 'under_review', 'Bills under verification.', 'agent_ravi'),
    ('aaaa3333-3333-3333-3333-333333333333', 'under_review', 'approved', 'Approved. Rs 2,000 not covered under OPD sub-limit.', 'manager_sunita'),

    -- CLM-2024-0004 history (submitted → under_review → denied)
    ('aaaa4444-4444-4444-4444-444444444444', NULL, 'submitted', 'Claim filed for flight delay compensation.', 'system'),
    ('aaaa4444-4444-4444-4444-444444444444', 'submitted', 'under_review', 'Reviewing airline delay certificate.', 'agent_meera'),
    ('aaaa4444-4444-4444-4444-444444444444', 'under_review', 'denied', 'Denied: Policy covers delays over 6 hours only. Actual delay was 3 hours.', 'manager_sunita'),

    -- CLM-2024-0005 history (submitted)
    ('aaaa5555-5555-5555-5555-555555555555', NULL, 'submitted', 'Claim submitted with photos of water damage.', 'system'),

    -- CLM-2024-0006 history (submitted → under_review → approved → paid → closed)
    ('aaaa6666-6666-6666-6666-666666666666', NULL, 'submitted', 'Claim filed with FIR copy and inventory list.', 'system'),
    ('aaaa6666-6666-6666-6666-666666666666', 'submitted', 'under_review', 'Investigator assigned. Verifying FIR and inventory.', 'agent_ravi'),
    ('aaaa6666-6666-6666-6666-666666666666', 'under_review', 'approved', 'Approved for Rs 1,20,000 after depreciation adjustment.', 'manager_sunita'),
    ('aaaa6666-6666-6666-6666-666666666666', 'approved', 'paid', 'Payment processed via NEFT.', 'system'),
    ('aaaa6666-6666-6666-6666-666666666666', 'paid', 'closed', 'Claim closed. Customer acknowledged receipt of payment.', 'system'),

    -- CLM-2024-0007 history (submitted → under_review)
    ('aaaa7777-7777-7777-7777-777777777777', NULL, 'submitted', 'Emergency claim submitted by hospital.', 'system'),
    ('aaaa7777-7777-7777-7777-777777777777', 'submitted', 'under_review', 'Medical records under review by panel doctor.', 'agent_meera'),

    -- CLM-2024-0010 history (submitted → denied)
    ('aaaabbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', NULL, 'submitted', 'Claim submitted for parking damage.', 'system'),
    ('aaaabbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'submitted', 'denied', 'Denied: Policy was cancelled on 2024-09-15, before incident date.', 'manager_sunita');


-- ===================
-- KNOWLEDGE BASE (15+ articles)
-- ===================

INSERT INTO knowledge_base (category, question, answer, tags)
VALUES
    -- Claims Process
    ('claims_process', 'How do I file a new insurance claim?', 
     'To file a new insurance claim, follow these steps:\n1. Log in to your account on our portal or mobile app\n2. Go to "My Policies" and select the relevant policy\n3. Click "File a Claim" and fill in the incident details\n4. Upload supporting documents (bills, FIR copy, photos, etc.)\n5. Submit the claim — you will receive a claim number via SMS and email\n\nAlternatively, you can call our 24/7 helpline at 1800-XXX-XXXX or visit your nearest branch.', 
     ARRAY['claim', 'file', 'new', 'submit', 'how to']),

    ('claims_process', 'What documents are required to file a claim?',
     'Documents vary by claim type:\n\n**Health Claims:**\n- Hospital discharge summary\n- Original bills and receipts\n- Prescription copies\n- Diagnostic reports\n- Pre-authorization letter (if cashless)\n\n**Auto Claims:**\n- FIR copy (for theft/major accident)\n- Driving license copy\n- RC book copy\n- Photos of damage\n- Repair estimate from authorized garage\n\n**Home Claims:**\n- FIR copy (for theft)\n- Photos/videos of damage\n- List of damaged/stolen items with value\n- Repair estimates\n\n**Travel Claims:**\n- Boarding passes and tickets\n- Medical bills (if medical claim)\n- Airline delay certificate\n- Hotel and food receipts',
     ARRAY['documents', 'required', 'proof', 'bills', 'receipts']),

    ('claims_process', 'How long does it take to process a claim?',
     'Typical claim processing timelines:\n\n- **Health (Cashless):** Pre-authorization within 2-4 hours, final settlement within 7-10 days after discharge\n- **Health (Reimbursement):** 15-30 days from document submission\n- **Auto:** 7-15 days after surveyor inspection\n- **Home:** 15-30 days depending on investigation\n- **Travel:** 10-20 days\n- **Life:** 30 days from submission of all documents\n\nComplex cases involving investigation may take longer. You can track your claim status anytime through our portal or by calling the helpline.',
     ARRAY['time', 'processing', 'duration', 'how long', 'timeline']),

    ('claims_process', 'How can I check my claim status?',
     'You can check your claim status through multiple channels:\n\n1. **Online Portal:** Log in at portal.insurance.com → My Claims → Enter claim number\n2. **Mobile App:** Open app → Claims tab → View status\n3. **SMS:** Send "STATUS <CLAIM_NUMBER>" to 56789\n4. **Helpline:** Call 1800-XXX-XXXX and provide your claim number\n5. **AI Agent:** Simply ask me! Provide your claim number (e.g., CLM-2024-0001) and I will fetch the latest status for you.\n\nClaim statuses: Submitted → Under Review → Approved/Denied → Paid → Closed',
     ARRAY['status', 'check', 'track', 'tracking', 'where']),

    ('claims_process', 'What happens if my claim is denied?',
     'If your claim is denied:\n\n1. **Review the denial reason** — You will receive a detailed letter explaining why\n2. **Gather additional evidence** — If you have supporting documents that address the denial reason\n3. **File an appeal** — Submit a written appeal within 30 days with additional documents\n4. **Escalate to Grievance Cell** — If appeal is rejected, contact our Grievance Redressal Officer\n5. **IRDAI Complaint** — As a last resort, file a complaint with the Insurance Regulatory Authority (IGMS portal)\n\nCommon denial reasons: Pre-existing condition exclusion, policy lapsed, waiting period not completed, insufficient documentation.',
     ARRAY['denied', 'rejected', 'appeal', 'grievance', 'complaint']),

    -- Policy Management
    ('policy_management', 'How do I renew my insurance policy?',
     'Policy renewal options:\n\n1. **Auto-Renewal:** If enabled, your policy renews automatically before expiry (payment charged to saved method)\n2. **Online:** Log in → My Policies → Click "Renew" → Review and pay\n3. **Mobile App:** Policies tab → Renew → Pay via UPI/Card/Net Banking\n4. **Branch Visit:** Visit nearest branch with policy number and ID proof\n\n**Important:** Renew before expiry to avoid:\n- Break in coverage\n- Loss of No Claim Bonus (auto insurance)\n- Waiting period reset (health insurance)\n\nGrace period: 30 days after expiry for most policies.',
     ARRAY['renew', 'renewal', 'expire', 'expiry', 'extend']),

    ('policy_management', 'How can I update my personal details on the policy?',
     'To update your personal information:\n\n**What can be updated:**\n- Address, phone number, email\n- Nominee details\n- Bank account for claims\n\n**What cannot be changed:**\n- Policyholder name (requires new policy)\n- Date of birth\n- Policy start date\n\n**How to update:**\n1. Log in to portal → Profile → Edit Details\n2. Submit supporting documents (address proof, ID proof)\n3. Changes reflect within 2-3 business days\n\nFor nominee changes, a signed endorsement form is required.',
     ARRAY['update', 'change', 'details', 'address', 'nominee', 'personal']),

    ('policy_management', 'How do I cancel my insurance policy?',
     'Policy cancellation process:\n\n1. **Free-Look Period (15 days):** Full refund minus stamp duty and medical exam costs\n2. **After Free-Look Period:** Pro-rata refund based on unused coverage period\n\n**Steps:**\n1. Submit written cancellation request via portal or branch\n2. Provide reason for cancellation\n3. Surrender original policy document\n4. Refund processed within 15 business days\n\n**Note:** Cancelling health insurance may result in loss of accumulated benefits and waiting period credits. Consider porting instead of cancelling.',
     ARRAY['cancel', 'cancellation', 'refund', 'surrender', 'stop']),

    -- Billing & Payments
    ('billing_payments', 'What payment methods are accepted for premiums?',
     'We accept the following payment methods:\n\n- **UPI:** Google Pay, PhonePe, Paytm, BHIM\n- **Credit/Debit Cards:** Visa, Mastercard, RuPay\n- **Net Banking:** All major Indian banks\n- **NEFT/RTGS:** Direct bank transfer\n- **Auto-Debit:** ECS/NACH mandate from bank account\n- **Cheque:** Payable at branch offices\n- **Wallets:** Paytm, Amazon Pay\n\nAll online payments are processed securely with 256-bit SSL encryption.',
     ARRAY['payment', 'pay', 'premium', 'method', 'upi', 'card', 'online']),

    ('billing_payments', 'Can I pay my premium in installments?',
     'Yes, we offer flexible premium payment options:\n\n| Frequency | Discount/Loading |\n|-----------|------------------|\n| Annual | 0% (base rate) |\n| Semi-Annual | +2% loading |\n| Quarterly | +4% loading |\n| Monthly | +5% loading |\n\n**How to switch:**\n1. Log in → My Policies → Payment Settings\n2. Select preferred frequency\n3. Set up auto-debit (recommended)\n\n**Note:** Switching frequency takes effect from the next renewal cycle. Monthly ECS/auto-debit is available for premiums above Rs 5,000/year.',
     ARRAY['installment', 'emi', 'monthly', 'quarterly', 'payment plan']),

    ('billing_payments', 'What happens if I miss a premium payment?',
     'If you miss a premium payment:\n\n1. **Grace Period (30 days):** Policy remains active. Pay within this window with no penalty.\n2. **After Grace Period:** Policy lapses. Coverage suspended.\n3. **Revival:** Policy can be revived within 2 years by:\n   - Paying all due premiums with interest\n   - Submitting a health declaration (for health/life insurance)\n   - Possible medical examination\n\n**Impact of lapse:**\n- No coverage during lapsed period\n- Health insurance waiting periods may reset\n- Auto insurance NCB may be lost\n\nWe send reminders via SMS and email 15, 7, and 3 days before due date.',
     ARRAY['missed', 'late', 'lapse', 'grace period', 'overdue']),

    -- Coverage Information
    ('coverage_info', 'What is not covered under health insurance?',
     'Common health insurance exclusions:\n\n**Permanent Exclusions:**\n- Cosmetic/aesthetic procedures\n- Self-inflicted injuries\n- War and nuclear risks\n- Adventure sports injuries (unless add-on purchased)\n- Substance abuse related treatment\n\n**Waiting Period Exclusions:**\n- Pre-existing diseases: 2-4 years\n- Specific diseases (hernia, cataract, etc.): 1-2 years\n- Maternity: 2-3 years\n\n**Sub-Limits:**\n- Room rent (1-2% of sum insured per day)\n- ICU charges\n- Ambulance charges (capped)\n\nRefer to your policy document for the complete exclusion list.',
     ARRAY['exclusion', 'not covered', 'excluded', 'limitation', 'health']),

    ('coverage_info', 'What is cashless treatment and how does it work?',
     'Cashless treatment means you don''t pay hospital bills upfront — we settle directly with the hospital.\n\n**How it works:**\n1. Get admitted to a network hospital (check list on our app/website)\n2. Show your health card at the hospital''s TPA desk\n3. Hospital sends pre-authorization request to us\n4. We approve/reject within 2-4 hours\n5. After discharge, hospital bills us directly\n6. You pay only non-covered items and deductible\n\n**Network hospitals:** 8,000+ hospitals across India\n\n**For planned procedures:** Request pre-authorization 3-5 days in advance for faster processing.',
     ARRAY['cashless', 'network', 'hospital', 'TPA', 'direct settlement']),

    ('coverage_info', 'What is No Claim Bonus (NCB) in auto insurance?',
     'No Claim Bonus (NCB) is a discount on your premium for every claim-free year.\n\n**NCB Slabs (as per IRDAI):**\n| Claim-Free Years | NCB Discount |\n|-----------------|-------------|\n| 1 year | 20% |\n| 2 years | 25% |\n| 3 years | 35% |\n| 4 years | 45% |\n| 5+ years | 50% |\n\n**Key points:**\n- NCB is earned by the policyholder, not the vehicle\n- NCB resets to 0% if a claim is made\n- NCB can be transferred when switching insurers\n- NCB is lost if policy lapses beyond 90 days\n\n**NCB Protect Add-on:** Available for an extra premium — lets you make 1 claim per year without losing NCB.',
     ARRAY['NCB', 'no claim bonus', 'discount', 'auto', 'car insurance']),

    -- General FAQ
    ('general_faq', 'How do I contact customer support?',
     'You can reach us through multiple channels:\n\n- **24/7 Helpline:** 1800-XXX-XXXX (toll-free)\n- **Email:** support@insurance.com\n- **WhatsApp:** +91-98765-XXXXX\n- **Live Chat:** Available on website and mobile app (9 AM - 9 PM)\n- **Branch Visit:** Find nearest branch at insurance.com/branches\n- **Social Media:** Twitter @InsuranceHelp, Facebook /InsuranceCo\n\n**For emergencies (hospitalization/accident):** Call our priority line 1800-XXX-9999',
     ARRAY['contact', 'support', 'helpline', 'phone', 'email', 'customer care']),

    ('general_faq', 'What is the difference between term and whole life insurance?',
     '**Term Life Insurance:**\n- Coverage for a specific period (10-40 years)\n- Lower premiums\n- No maturity benefit (death benefit only)\n- Best for: Income replacement, loan coverage\n- Example: Rs 1 Cr cover for Rs 10,000-15,000/year (age 30)\n\n**Whole Life Insurance:**\n- Coverage for entire lifetime (up to age 99-100)\n- Higher premiums\n- Has cash value component / maturity benefit\n- Best for: Estate planning, wealth transfer\n- Example: Rs 50 Lakh cover for Rs 30,000-50,000/year (age 30)\n\n**Recommendation:** Term insurance offers the best value for pure protection needs.',
     ARRAY['term', 'whole life', 'difference', 'life insurance', 'comparison']),

    ('general_faq', 'Is insurance premium tax deductible?',
     'Yes, insurance premiums offer tax benefits under the Income Tax Act:\n\n**Section 80C (Life Insurance):**\n- Deduction up to Rs 1,50,000/year\n- Covers life insurance and ULIP premiums\n\n**Section 80D (Health Insurance):**\n- Self & family: Up to Rs 25,000 (Rs 50,000 if senior citizen)\n- Parents: Additional Rs 25,000 (Rs 50,000 if senior citizen)\n- Preventive health checkup: Rs 5,000 (within above limits)\n\n**Section 10(10D):**\n- Death benefit and maturity proceeds are tax-free (conditions apply)\n\n**Note:** These limits are as per current tax laws and may change. Consult a tax advisor for personalized advice.',
     ARRAY['tax', 'deduction', '80C', '80D', 'tax benefit', 'income tax']);
