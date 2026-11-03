"""
Head-to-Head Latency & Accuracy Benchmark: Jev (TypeSafe AI) vs Router LLMs.

Evaluates:
1. Intent Classification Accuracy (%) against ground truth
2. Latency metrics: Mean, Median (P50), P90, P95, P99
3. Net latency gain and percentage reduction

Usage:
    python eval/benchmark_router.py
"""

import asyncio
import json
import logging
import math
import os
import sys
import time
from typing import Dict, Any, List

from dotenv import load_dotenv

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from typesafe_sdk import AsyncTypeSafeClient

from agent.agent import _INTENT_CHOICE
from agent.config import ROUTER_PROMPT
from eval.dataset import ROUTER_EVAL_DATASET
from eval.evaluators import evaluate_router_prediction

load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))
logging.basicConfig(level=logging.WARNING)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def percentile(data: List[float], p: float) -> float:
    """Calculate the p-th percentile of a list of floats (0 <= p <= 100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1


# ── 1. Runner for Jev (TypeSafe AI) ──────────────────────────────────────────

async def run_jev_query(client: AsyncTypeSafeClient, query: str) -> tuple[str, float]:
    """Runs a single query through Jev System One."""
    t0 = time.perf_counter()
    response = await client.system_one(
        state=query,
        questions={"intent": _INTENT_CHOICE},
    )
    dur_ms = (time.perf_counter() - t0) * 1000.0

    answer = response.choices.get("intent")
    raw_choice = answer.choice if answer else "knowledge_base"
    intent_map = {
        "knowledge_base": "KNOWLEDGE_BASE",
        "transactional": "TRANSACTIONAL",
        "mixed": "MIXED",
        "out_of_scope": "OUT_OF_SCOPE",
    }
    return intent_map.get(raw_choice, "KNOWLEDGE_BASE"), dur_ms


# ── 2. Runner for Router LLM ────────────────────────────────────────────────

async def run_llm_query(llm: ChatOpenAI, query: str) -> tuple[str, float]:
    """Runs a single query through an LLM using the classic JSON prompt."""
    messages = [
        SystemMessage(content=ROUTER_PROMPT),
        HumanMessage(content=f"Classify this query: {query}"),
    ]
    t0 = time.perf_counter()
    response = await llm.ainvoke(messages)
    dur_ms = (time.perf_counter() - t0) * 1000.0

    content = response.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        data = json.loads(content)
        intent = data.get("intent", "TRANSACTIONAL").upper()
        if "MIXED" in intent:
            res_intent = "MIXED"
        elif "KNOWLEDGE" in intent:
            res_intent = "KNOWLEDGE_BASE"
        elif "SCOPE" in intent or "OUT" in intent:
            res_intent = "OUT_OF_SCOPE"
        else:
            res_intent = "TRANSACTIONAL"
    except Exception:
        res_intent = "KNOWLEDGE_BASE"

    return res_intent, dur_ms


# ── 3. Benchmark Suite ───────────────────────────────────────────────────────

async def benchmark_method(name: str, fn, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    print(f"\n--> Benchmarking: {name} ({len(dataset)} queries)...", flush=True)
    latencies: List[float] = []
    correct = 0
    errors = 0

    # Warm-up (1 query) to eliminate cold connection / initial SSL handshake bias
    try:
        await fn(dataset[0]["query"])
    except Exception:
        pass

    for item in dataset:
        query = item["query"]
        expected = item["expected_intent"]
        try:
            predicted, dur_ms = await fn(query)
            latencies.append(dur_ms)
            eval_res = evaluate_router_prediction(predicted, expected)
            if eval_res["passed"]:
                correct += 1
                status = "[PASS]"
            else:
                status = f"[FAIL: got {predicted}]"
            print(f"   [{item['id']}] {status:20} | {dur_ms:6.1f} ms | {query[:45]}...", flush=True)
        except Exception as e:
            errors += 1
            print(f"   [{item['id']}] [ERROR]: {e}", flush=True)

    total = len(dataset)
    acc = (correct / total) * 100.0 if total else 0.0
    mean_lat = sum(latencies) / len(latencies) if latencies else 0.0

    return {
        "name": name,
        "total": total,
        "correct": correct,
        "accuracy": round(acc, 1),
        "errors": errors,
        "mean_ms": round(mean_lat, 1),
        "p50_ms": round(percentile(latencies, 50), 1),
        "p90_ms": round(percentile(latencies, 90), 1),
        "p95_ms": round(percentile(latencies, 95), 1),
        "p99_ms": round(percentile(latencies, 99), 1),
        "min_ms": round(min(latencies), 1) if latencies else 0.0,
        "max_ms": round(max(latencies), 1) if latencies else 0.0,
    }


async def main():
    print("=" * 80, flush=True)
    print(" ROUTER INTENT BENCHMARK: JEV vs ROUTER LLM", flush=True)
    print("=" * 80, flush=True)

    dataset = ROUTER_EVAL_DATASET

    # 1. Initialize Jev
    typesafe_key = os.getenv("TYPESAFE_API_KEY")
    if not typesafe_key:
        print("[ERROR] TYPESAFE_API_KEY is missing from environment.", flush=True)
        return
    jev_client = AsyncTypeSafeClient(api_key=typesafe_key, model="jev-latest")

    # 2. Initialize OpenAI Router LLM (gpt-4o-mini is standard fast router)
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = "gpt-4o-mini"
    openai_llm = ChatOpenAI(model=openai_model, api_key=openai_key, temperature=0.0) if openai_key else None

    results = []

    # Run Jev
    jev_res = await benchmark_method(
        "Jev (TypeSafe AI jev-latest)",
        lambda q: run_jev_query(jev_client, q),
        dataset,
    )
    results.append(jev_res)

    # Run OpenAI LLM
    if openai_llm:
        openai_res = await benchmark_method(
            f"Router LLM ({openai_model})",
            lambda q: run_llm_query(openai_llm, q),
            dataset,
        )
        results.append(openai_res)


    # Display Summary Comparison Table
    print("\n" + "=" * 92)
    print(f"{'Method':<34} | {'Accuracy':<9} | {'P50':<8} | {'P90':<8} | {'P95':<8} | {'Mean':<8}")
    print("=" * 92)
    for r in results:
        print(
            f"{r['name']:<34} | {r['accuracy']:>6.1f}%  | {r['p50_ms']:>6.1f}ms | "
            f"{r['p90_ms']:>6.1f}ms | {r['p95_ms']:>6.1f}ms | {r['mean_ms']:>6.1f}ms"
        )
    print("=" * 92)

    # Comparison Analysis
    if len(results) >= 2:
        baseline = results[1]
        jev = results[0]
        p50_diff = baseline["p50_ms"] - jev["p50_ms"]
        p50_pct = (p50_diff / baseline["p50_ms"]) * 100.0 if baseline["p50_ms"] else 0.0

        p95_diff = baseline["p95_ms"] - jev["p95_ms"]
        p95_pct = (p95_diff / baseline["p95_ms"]) * 100.0 if baseline["p95_ms"] else 0.0

        print("\nNET GAIN SUMMARY (Jev vs Traditional Router LLM):")
        print(f" * Median (P50) Latency Saved: {p50_diff:+.1f} ms  ({p50_pct:+.1f}% faster)")
        print(f" * Tail (P95) Latency Saved:   {p95_diff:+.1f} ms  ({p95_pct:+.1f}% faster)")
        print(f" * Accuracy Delta:             {jev['accuracy'] - baseline['accuracy']:+.1f}%")
        if p50_diff > 0:
            speedup = baseline["p50_ms"] / jev["p50_ms"] if jev["p50_ms"] else 1.0
            print(f" * Overall Speedup:            ~{speedup:.1f}x faster on median turn startup time!\n")
    print("=" * 92)


if __name__ == "__main__":
    asyncio.run(main())

