"""
Ground-truth evaluation datasets for the Insurance Policy Agent.
Covers:
1. Router Classification (Intent routing)
2. Tool Selection & Argument Extraction
3. RAG Groundedness & Faithfulness
4. Multi-turn Conversational Scenarios
"""

ROUTER_EVAL_DATASET = [
    # Knowledge Base Queries
    {
        "id": "router_kb_01",
        "query": "How do I file a cashless health insurance claim?",
        "expected_intent": "KNOWLEDGE_BASE",
        "category": "claims_process"
    },
    {
        "id": "router_kb_02",
        "query": "What is No Claim Bonus (NCB) and how is it calculated?",
        "expected_intent": "KNOWLEDGE_BASE",
        "category": "benefits"
    },
    {
        "id": "router_kb_03",
        "query": "Are health insurance premiums tax deductible under 80D?",
        "expected_intent": "KNOWLEDGE_BASE",
        "category": "tax"
    },
    {
        "id": "router_kb_04",
        "query": "What documents are required for accidental car damage claim?",
        "expected_intent": "KNOWLEDGE_BASE",
        "category": "claims_process"
    },
    {
        "id": "router_kb_05",
        "query": "What is the waiting period for pre-existing diseases?",
        "expected_intent": "KNOWLEDGE_BASE",
        "category": "coverage"
    },
    {
        "id": "router_kb_06",
        "query": "Can I cancel my insurance policy during the free-look period?",
        "expected_intent": "KNOWLEDGE_BASE",
        "category": "policy_rules"
    },
    {
        "id": "router_kb_07",
        "query": "How do I add my newborn baby to my existing family floater plan?",
        "expected_intent": "KNOWLEDGE_BASE",
        "category": "endorsement"
    },
    {
        "id": "router_kb_08",
        "query": "What is the difference between comprehensive and third-party car insurance?",
        "expected_intent": "KNOWLEDGE_BASE",
        "category": "coverage"
    },

    # Transactional Queries
    {
        "id": "router_tx_01",
        "query": "What is the status of my claim? My registered phone is +91-9876543210",
        "expected_intent": "TRANSACTIONAL",
        "category": "claim_status"
    },
    {
        "id": "router_tx_02",
        "query": "Can you check my active policies for amit.kumar@example.com?",
        "expected_intent": "TRANSACTIONAL",
        "category": "policy_info"
    },
    {
        "id": "router_tx_03",
        "query": "I want to see my customer profile details for phone 9876543210",
        "expected_intent": "TRANSACTIONAL",
        "category": "customer_info"
    },
    {
        "id": "router_tx_04",
        "query": "Show me claim status for claim number CLM-2024-0005",
        "expected_intent": "TRANSACTIONAL",
        "category": "claim_status"
    },
    {
        "id": "router_tx_05",
        "query": "When is my car insurance policy POL-MOT-2023-089 expiring?",
        "expected_intent": "TRANSACTIONAL",
        "category": "policy_info"
    },
    {
        "id": "router_tx_06",
        "query": "How many pending claims do I currently have registered on 919876543210?",
        "expected_intent": "TRANSACTIONAL",
        "category": "claim_status"
    },
]


TOOL_EVAL_DATASET = [
    {
        "id": "tool_01",
        "query": "Check status of all my claims. Phone number: +91-9876543210",
        "expected_tool": "check_claim_status",
        "expected_args": {
            "phone_number": "+91-9876543210"
        }
    },
    {
        "id": "tool_02",
        "query": "Look up customer account for email priya.sharma@example.com",
        "expected_tool": "get_customer_info",
        "expected_args": {
            "email": "priya.sharma@example.com"
        }
    },
    {
        "id": "tool_03",
        "query": "Find customer details for phone 9876543210",
        "expected_tool": "get_customer_info",
        "expected_args": {
            "phone": "9876543210"
        }
    },
    {
        "id": "tool_04",
        "query": "What are the rules and steps to file a reimbursement claim?",
        "expected_tool": "search_knowledge_base",
        "expected_args_key": "query"
    },
    {
        "id": "tool_05",
        "query": "Give me policy coverage details for policy number POL-HOM-2024-001",
        "expected_tool": "get_policy_info",
        "expected_args": {
            "policy_number": "POL-HOM-2024-001"
        }
    }
]


RAG_EVAL_DATASET = [
    {
        "id": "rag_01",
        "query": "How do I file a cashless claim at a network hospital?",
        "expected_key_points": [
            "Network hospital admission",
            "Show health card or policy copy at TPA desk",
            "Pre-authorization form submission",
            "Insurer approves pre-auth",
            "Hospital settles bill directly with insurer"
        ],
        "must_not_contain": [
            "Cash payment of full hospital bill required in advance for cashless"
        ]
    },
    {
        "id": "rag_02",
        "query": "What is No Claim Bonus (NCB) in motor insurance?",
        "expected_key_points": [
            "Discount on own-damage premium",
            "Earned for claim-free policy years",
            "Transfers with the owner, not the vehicle"
        ],
        "must_not_contain": [
            "NCB applies to third-party premium"
        ]
    },
    {
        "id": "rag_03",
        "query": "Is maternity covered under individual health insurance?",
        "expected_key_points": [
            "Depends on policy terms and waiting period",
            "Standard waiting period typically applies"
        ]
    }
]


MULTI_TURN_EVAL_DATASET = [
    {
        "id": "multi_turn_01",
        "conversation": [
            {
                "user": "Hi, I want to check my claim status.",
                "expected_response_type": "clarification_for_credentials"
            },
            {
                "user": "My phone number is +91-9876543210",
                "expected_tool_call": "check_claim_status"
            },
            {
                "user": "Can you also show the details of my home insurance policy?",
                "expected_tool_call": "get_policy_info"
            }
        ]
    }
]
