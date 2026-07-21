import uuid
import random
import time
import requests
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
    wait_time = between(1, 3)

    def on_start(self):
        self.thread_id = str(uuid.uuid4())
        self.client.headers.update({"Content-Type": "application/json"})

    def on_stop(self):
        pass

    def _new_thread(self):
        self.thread_id = str(uuid.uuid4())

    def _fire_request(self, name, response_time=None, response_length=0, exception=None):
        self.environment.events.request.fire(
            request_type="POST",
            name=name,
            response_time=response_time,
            response_length=response_length,
            exception=exception,
            context={},
        )

    @tag("chat", "knowledge")
    @task(3)
    def ask_kb_question(self):
        self._new_thread()
        query = random.choice(KB_QUERIES)
        payload = {"message": query, "thread_id": self.thread_id}

        with self.client.post("/chat", name="/chat (KB)", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                data = resp.json()
                if "error" in data:
                    resp.failure(f"API Error: {data['error']}")

    @tag("chat", "transactional")
    @task(1)
    def ask_transactional_question(self):
        self._new_thread()
        query = random.choice(TRANSACTIONAL_QUERIES)
        payload = {"message": query, "thread_id": self.thread_id}

        with self.client.post("/chat", name="/chat (Transactional)", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                data = resp.json()
                if "error" in data:
                    resp.failure(f"API Error: {data['error']}")

    @tag("stream", "knowledge")
    @task(2)
    def stream_kb_question(self):
        self._new_thread()
        query = random.choice(KB_QUERIES)
        payload = {"message": query, "thread_id": self.thread_id}
        base_url = self.environment.host.rstrip("/")
        name = "/chat/stream (KB)"

        start = time.perf_counter()
        try:
            resp = requests.post(
                f"{base_url}/chat/stream",
                json=payload,
                stream=True,
                timeout=120,
            )
            if resp.status_code != 200:
                resp.close()
                self._fire_request(name, exception=Exception(f"HTTP {resp.status_code}"))
                return

            chunk_count = 0
            for line in resp.iter_lines(decode_unicode=True):
                if line and line.startswith("data: ") and line != "data: [DONE]":
                    chunk_count += 1
            resp.close()
            elapsed = (time.perf_counter() - start) * 1000

            if chunk_count == 0:
                self._fire_request(name, exception=Exception("No chunks received"))
            else:
                self._fire_request(name, response_time=elapsed, response_length=chunk_count)
        except Exception as e:
            self._fire_request(name, exception=e)
