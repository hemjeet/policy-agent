"""
Evaluation Runner CLI for Insurance Policy Agent.

Executes test suites across:
1. Router Intent Classification Accuracy
2. Tool Calling & Parameter Extraction Accuracy
3. RAG Groundedness & Answer Relevance (LLM-as-a-Judge)
4. Latency & Token Metrics

Usage:
    python eval/run_evals.py
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.agent import PolicyAgent
from app import _build_llm, _init_vectorstore
from langchain_openai import OpenAIEmbeddings

from eval.dataset import (
    ROUTER_EVAL_DATASET,
    TOOL_EVAL_DATASET,
    RAG_EVAL_DATASET,
)
from eval.evaluators import (
    evaluate_router_prediction,
    evaluate_tool_call,
    evaluate_rag_response_with_judge,
    evaluate_key_points_coverage,
)

load_dotenv()
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("eval_runner")


class PolicyAgentEvaluator:
    def __init__(self):
        self.llm, self.router_llm = _build_llm()
        self.checkpointer = MemorySaver()
        self.agent = PolicyAgent(
            router_llm=self.router_llm,
            llm=self.llm,
            checkpointer=self.checkpointer,
        )
        self.graph = self.agent.graph

        # Initialize vectorstore if possible
        postgres_uri = os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL") or None
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.vectorstore = _init_vectorstore(postgres_uri, embeddings) if postgres_uri else None

    # ── 1. Evaluate Router ────────────────────────────────────────────────
    async def run_router_evals(self) -> Dict[str, Any]:
        print("\n🔍 Running [1/3] Router Intent Classification Evaluation...")
        results = []
        correct = 0
        total = len(ROUTER_EVAL_DATASET)
        latencies = []

        for item in ROUTER_EVAL_DATASET:
            query = item["query"]
            expected = item["expected_intent"]
            state = {"messages": [HumanMessage(content=query)]}

            t0 = time.perf_counter()
            try:
                predicted = await self.agent._router_llm(state)
            except Exception as e:
                predicted = f"ERROR: {e}"
            dur = time.perf_counter() - t0
            latencies.append(dur)

            eval_res = evaluate_router_prediction(predicted, expected)
            if eval_res["passed"]:
                correct += 1
                status = "✅ PASS"
            else:
                status = f"❌ FAIL (got {predicted})"

            print(f"  [{item['id']}] {status} | Query: '{query[:45]}...' ({dur:.2f}s)")
            results.append({
                "id": item["id"],
                "query": query,
                "expected": expected,
                "predicted": predicted,
                "passed": eval_res["passed"],
                "latency": round(dur, 2)
            })

        acc = (correct / total) * 100 if total else 0
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        print(f"  → Router Accuracy: {acc:.1f}% ({correct}/{total} passed) | Avg Latency: {avg_lat:.2f}s")

        return {
            "accuracy": round(acc, 1),
            "passed": correct,
            "total": total,
            "avg_latency": round(avg_lat, 2),
            "details": results
        }

    # ── 2. Evaluate Tool Calls ────────────────────────────────────────────
    async def run_tool_evals(self) -> Dict[str, Any]:
        print("\n🛠️  Running [2/3] Tool Selection & Argument Extraction Evaluation...")
        results = []
        tool_correct = 0
        args_correct = 0
        total = len(TOOL_EVAL_DATASET)
        latencies = []

        for item in TOOL_EVAL_DATASET:
            query = item["query"]
            expected_tool = item.get("expected_tool")
            expected_args = item.get("expected_args")

            t0 = time.perf_counter()
            config = {
                "configurable": {
                    "thread_id": f"eval_tool_{item['id']}",
                    "vectorstore": self.vectorstore
                }
            }

            actual_tool_calls = []

            try:
                async for event in self.graph.astream(
                    {"messages": [HumanMessage(content=query)]},
                    config=config
                ):
                    for node_name, node_output in event.items():
                        msgs = node_output.get("messages", [])
                        for msg in msgs:
                            if isinstance(msg, AIMessage) and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    actual_tool_calls.append({
                                        "name": tc["name"],
                                        "args": tc.get("args", {})
                                    })
            except Exception as e:
                logger.error("Tool eval error: %s", e)

            dur = time.perf_counter() - t0
            latencies.append(dur)

            eval_res = evaluate_tool_call(actual_tool_calls, expected_tool, expected_args)
            if eval_res["tool_match"]:
                tool_correct += 1
            if eval_res["args_match"]:
                args_correct += 1

            status = "✅ PASS" if (eval_res["tool_match"] and eval_res["args_match"]) else "❌ FAIL"
            tools_called = eval_res['actual_tools']
            print(f"  [{item['id']}] {status} | Expected: {expected_tool} | Called: {tools_called} ({dur:.2f}s)")

            results.append({
                "id": item["id"],
                "query": query,
                "expected_tool": expected_tool,
                "expected_args": expected_args,
                "actual_tools": eval_res["actual_tools"],
                "tool_match": eval_res["tool_match"],
                "args_match": eval_res["args_match"],
                "latency": round(dur, 2)
            })

        tool_acc = (tool_correct / total) * 100 if total else 0
        args_acc = (args_correct / total) * 100 if total else 0
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        print(f"  → Tool Selection Accuracy: {tool_acc:.1f}% ({tool_correct}/{total})")
        print(f"  → Argument Extraction Accuracy: {args_acc:.1f}% ({args_correct}/{total})")

        return {
            "tool_selection_accuracy": round(tool_acc, 1),
            "argument_extraction_accuracy": round(args_acc, 1),
            "total": total,
            "avg_latency": round(avg_lat, 2),
            "details": results
        }

    # ── 3. Evaluate RAG Groundedness & Relevance ──────────────────────────
    async def run_rag_evals(self) -> Dict[str, Any]:
        print("\n📚 Running [3/3] RAG Quality & Groundedness Evaluation...")
        results = []
        groundedness_scores = []
        relevance_scores = []
        coverage_scores = []
        latencies = []

        for item in RAG_EVAL_DATASET:
            query = item["query"]
            expected_key_points = item.get("expected_key_points", [])

            t0 = time.perf_counter()
            config = {
                "configurable": {
                    "thread_id": f"eval_rag_{item['id']}",
                    "vectorstore": self.vectorstore
                }
            }

            final_response = ""
            retrieved_context = ""

            try:
                async for event in self.graph.astream(
                    {"messages": [HumanMessage(content=query)]},
                    config=config
                ):
                    for node_name, node_output in event.items():
                        msgs = node_output.get("messages", [])
                        for msg in msgs:
                            if isinstance(msg, AIMessage) and msg.content:
                                final_response = msg.content
                            # Check tool response for context
                            if hasattr(msg, "content") and "answer" in str(msg.content):
                                retrieved_context += str(msg.content)
            except Exception as e:
                logger.error("RAG eval error: %s", e)

            dur = time.perf_counter() - t0
            latencies.append(dur)

            # 1. Deterministic keypoint coverage
            cov_res = evaluate_key_points_coverage(final_response, expected_key_points)
            coverage_scores.append(cov_res["coverage_pct"])

            # 2. LLM-as-a-Judge
            judge_res = await evaluate_rag_response_with_judge(
                self.llm,
                query=query,
                context=retrieved_context or "Insurance Knowledge Base",
                response=final_response
            )
            groundedness_scores.append(judge_res["groundedness"])
            relevance_scores.append(judge_res["relevance"])

            g_score = judge_res['groundedness']
            r_score = judge_res['relevance']
            cov = cov_res['coverage_pct']
            print(f"  [{item['id']}] Groundedness: {g_score}/5 | Relevance: {r_score}/5 | Cov: {cov}% ({dur:.2f}s)")

            results.append({
                "id": item["id"],
                "query": query,
                "response": final_response[:200] + "...",
                "groundedness": judge_res["groundedness"],
                "relevance": judge_res["relevance"],
                "coverage_pct": cov_res["coverage_pct"],
                "reason": judge_res["reason"],
                "latency": round(dur, 2)
            })

        avg_groundedness = sum(groundedness_scores) / len(groundedness_scores) if groundedness_scores else 0
        avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0
        avg_cov = sum(coverage_scores) / len(coverage_scores) if coverage_scores else 0
        avg_lat = sum(latencies) / len(latencies) if latencies else 0

        print(f"  → Avg Groundedness: {avg_groundedness:.2f} / 5.0")
        print(f"  → Avg Relevance:    {avg_relevance:.2f} / 5.0")
        print(f"  → Avg Keypoint Coverage: {avg_cov:.1f}%")

        return {
            "avg_groundedness": round(avg_groundedness, 2),
            "avg_relevance": round(avg_relevance, 2),
            "avg_keypoint_coverage": round(avg_cov, 1),
            "avg_latency": round(avg_lat, 2),
            "details": results
        }


async def main():
    print("=" * 70)
    print("        🚀 STARTING POLICY AGENT AUTOMATED EVALUATION SUITE")
    print("=" * 70)
    start_time = datetime.now()

    evaluator = PolicyAgentEvaluator()

    router_metrics = await evaluator.run_router_evals()
    tool_metrics = await evaluator.run_tool_evals()
    rag_metrics = await evaluator.run_rag_evals()

    total_duration = (datetime.now() - start_time).total_seconds()

    summary_report = {
        "timestamp": datetime.now().isoformat(),
        "total_duration_seconds": round(total_duration, 2),
        "metrics": {
            "router_accuracy_pct": router_metrics["accuracy"],
            "tool_selection_accuracy_pct": tool_metrics["tool_selection_accuracy"],
            "argument_extraction_accuracy_pct": tool_metrics["argument_extraction_accuracy"],
            "rag_groundedness_score_out_of_5": rag_metrics["avg_groundedness"],
            "rag_relevance_score_out_of_5": rag_metrics["avg_relevance"],
            "rag_keypoint_coverage_pct": rag_metrics["avg_keypoint_coverage"],
            "router_avg_latency_s": router_metrics["avg_latency"],
            "tool_avg_latency_s": tool_metrics["avg_latency"],
            "rag_avg_latency_s": rag_metrics["avg_latency"],
        },
        "results": {
            "router": router_metrics,
            "tool_calling": tool_metrics,
            "rag": rag_metrics
        }
    }

    # Save JSON Report
    os.makedirs("eval/reports", exist_ok=True)
    json_path = "eval/reports/eval_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2)

    # Save Markdown Report
    md_path = "eval/reports/eval_report.md"
    r_stat = '✅ Pass' if router_metrics['accuracy'] >= 90 else '⚠️ Needs Attention'
    t_stat = '✅ Pass' if tool_metrics['tool_selection_accuracy'] >= 90 else '⚠️ Needs Attention'
    a_stat = '✅ Pass' if tool_metrics['argument_extraction_accuracy'] >= 85 else '⚠️ Needs Attention'
    rg_stat = '✅ Pass' if rag_metrics['avg_groundedness'] >= 4.0 else '⚠️ Needs Attention'
    rr_stat = '✅ Pass' if rag_metrics['avg_relevance'] >= 4.0 else '⚠️ Needs Attention'
    c_stat = '✅ Pass' if rag_metrics['avg_keypoint_coverage'] >= 80 else '⚠️ Needs Attention'

    md_content = f"""# 📊 Policy Agent Evaluation Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary Scorecard
| Metric | Score | Target | Status |
|--------|-------|--------|--------|
| **Router Intent Accuracy** | {router_metrics['accuracy']}% | ≥ 90% | {r_stat} |
| **Tool Selection Accuracy** | {tool_metrics['tool_selection_accuracy']}% | ≥ 90% | {t_stat} |
| **Argument Extraction Accuracy** | {tool_metrics['argument_extraction_accuracy']}% | ≥ 85% | {a_stat} |
| **RAG Groundedness** | {rag_metrics['avg_groundedness']} / 5.0 | ≥ 4.0 | {rg_stat} |
| **RAG Answer Relevance** | {rag_metrics['avg_relevance']} / 5.0 | ≥ 4.0 | {rr_stat} |
| **Keypoint Coverage** | {rag_metrics['avg_keypoint_coverage']}% | ≥ 80% | {c_stat} |

*Total evaluation time: {total_duration:.2f}s*
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n" + "=" * 70)
    print("                      🎉 EVALUATION SUMMARY")
    print("=" * 70)
    print(f"  • Router Intent Accuracy:        {router_metrics['accuracy']}%")
    print(f"  • Tool Selection Accuracy:       {tool_metrics['tool_selection_accuracy']}%")
    print(f"  • Argument Extraction Accuracy:   {tool_metrics['argument_extraction_accuracy']}%")
    print(f"  • RAG Groundedness (Faithful):   {rag_metrics['avg_groundedness']} / 5.0")
    print(f"  • RAG Answer Relevance:          {rag_metrics['avg_relevance']} / 5.0")
    print(f"  • Keypoint Coverage:             {rag_metrics['avg_keypoint_coverage']}%")
    print("=" * 70)
    print("📄 Reports saved to:")
    print(f"   - {json_path}")
    print(f"   - {md_path}")
    print("=" * 70)

    # ── Quality Gate Evaluation (Cut-offs) ──────────────────────────────
    router_min = float(os.getenv("EVAL_ROUTER_MIN_ACCURACY", "90.0"))
    tool_min = float(os.getenv("EVAL_TOOL_MIN_ACCURACY", "85.0"))
    rag_ground_min = float(os.getenv("EVAL_RAG_MIN_GROUNDEDNESS", "3.8"))
    rag_rel_min = float(os.getenv("EVAL_RAG_MIN_RELEVANCE", "3.8"))

    failures = []
    if router_metrics["accuracy"] < router_min:
        failures.append(f"Router Accuracy {router_metrics['accuracy']}% < required {router_min}%")
    if tool_metrics["tool_selection_accuracy"] < tool_min:
        failures.append(f"Tool Selection Accuracy {tool_metrics['tool_selection_accuracy']}% < required {tool_min}%")
    if rag_metrics["avg_groundedness"] < rag_ground_min:
        failures.append(f"RAG Groundedness {rag_metrics['avg_groundedness']} < required {rag_ground_min}")
    if rag_metrics["avg_relevance"] < rag_rel_min:
        failures.append(f"RAG Relevance {rag_metrics['avg_relevance']} < required {rag_rel_min}")

    print("\n" + "=" * 70)
    print("                      🎯 QUALITY GATE STATUS")
    print("=" * 70)
    if failures:
        print("❌ EVALUATION FAILED — QUALITY GATES NOT MET! BLOCKING DEPLOYMENT.")
        for f_msg in failures:
            print(f"   🚫 {f_msg}")
        print("=" * 70)
        sys.exit(1)
    else:
        print("✅ ALL QUALITY GATES PASSED! READY FOR DEPLOYMENT.")
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
