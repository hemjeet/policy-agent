import uuid
import random
from locust import HttpUser, task, between, tag

KB_QUERIES = [
    "How do I file a health insurance claim?",
    "What is No Claim Bonus?",
    "Is my health insurance premium tax deductible?",
    "What documents do I need for a motor claim?",
    "How do I port my health insurance?",
    "What is not covered under health insurance?",
]

TRANSACTIONAL_QUERIES = [
    "What is the status of my claims? My registered phone number is +91-9876543210.",
    "Can you check my claim status? Phone is +91-8765432109.",
    "I registered with phone number +91-9876543210. Do I have any pending claims?",
    "Show me my claims for +91-8765432109.",
]

class PolicyAgentUser(HttpUser):
    # Wait between 1 and 3 seconds between tasks
    wait_time = between(1, 3)

    def on_start(self):
        # Generate a unique thread ID for this simulated user
        self.thread_id = str(uuid.uuid4())
        self.client.headers.update({"Content-Type": "application/json"})

    @tag("chat", "knowledge")
    @task(3)
    def ask_kb_question(self):
        query = random.choice(KB_QUERIES)
        payload = {"message": query, "thread_id": self.thread_id}
        
        with self.client.post("/chat", name="/chat (KB)", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                data = resp.json()
                if "error" in data:
                    resp.failure(f"API Error: {data['error']}")
                elif "knowledge base" in data.get("response", "").lower()[:200]:
                    resp.failure("Agent reported KB miss when it should have results")

    @tag("chat", "transactional")
    @task(1)
    def ask_transactional_question(self):
        query = random.choice(TRANSACTIONAL_QUERIES)
        payload = {"message": query, "thread_id": self.thread_id}
        
        with self.client.post("/chat", name="/chat (Transactional)", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")

    @tag("stream", "knowledge")
    @task(2)
    def stream_kb_question(self):
        query = random.choice(KB_QUERIES)
        payload = {"message": query, "thread_id": self.thread_id}

        try:
            with self.client.post(
                "/chat/stream",
                name="/chat/stream (KB)",
                json=payload,
                catch_response=True,
                timeout=120,
                stream=True,
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    return
                chunk_count = 0
                for line in resp.iter_lines(decode_unicode=True):
                    if line and line != "data: [DONE]":
                        chunk_count += 1
                if chunk_count == 0:
                    resp.failure("No chunks received in stream")
        except Exception as e:
            pass  # Already marked as failure by timeout
        
        # Reset thread_id after a streaming call to simulate a new chat
        self.thread_id = str(uuid.uuid4())
