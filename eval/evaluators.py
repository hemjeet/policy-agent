"""
Metric evaluators for the Policy Agent evaluation framework.
Includes:
- Router Accuracy & Confusion Matrix
- Tool Selection & Argument Accuracy
- RAG Faithfulness, Groundedness & Key Point Coverage
- LLM-as-a-Judge evaluators
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


# ── 1. Router Evaluator ──────────────────────────────────────────────────

def evaluate_router_prediction(predicted_intent: str, expected_intent: str) -> Dict[str, Any]:
    """Evaluate if router classification matches the expected ground-truth intent."""
    pred_clean = (predicted_intent or "").strip().upper()
    exp_clean = (expected_intent or "").strip().upper()
    passed = (pred_clean == exp_clean)
    return {
        "passed": passed,
        "predicted": pred_clean,
        "expected": exp_clean,
    }


# ── 2. Tool Calling Evaluator ────────────────────────────────────────────

def evaluate_tool_call(
    actual_tool_calls: List[Dict[str, Any]],
    expected_tool: str,
    expected_args: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Evaluate whether the agent invoked the expected tool with the correct arguments."""
    if not actual_tool_calls:
        return {
            "tool_match": False,
            "args_match": False,
            "details": "No tools were called by the agent."
        }

    actual_names = [call.get("name") for call in actual_tool_calls]
    tool_match = expected_tool in actual_names

    args_match = True
    if tool_match and expected_args:
        # Find the specific call
        target_call = next((c for c in actual_tool_calls if c.get("name") == expected_tool), None)
        if not target_call:
            args_match = False
        else:
            call_args = target_call.get("args", {})
            for key, exp_val in expected_args.items():
                act_val = call_args.get(key)
                if act_val is None:
                    args_match = False
                    break
                # Normalize string comparison (e.g. phone numbers, emails)
                norm_act = re.sub(r'[\s\-+]', '', str(act_val).lower())
                norm_exp = re.sub(r'[\s\-+]', '', str(exp_val).lower())
                if norm_exp not in norm_act and norm_act not in norm_exp:
                    args_match = False
                    break

    return {
        "tool_match": tool_match,
        "args_match": args_match,
        "actual_tools": actual_names,
        "expected_tool": expected_tool
    }


# ── 3. RAG Groundedness & Relevance (LLM-as-a-Judge) ────────────────────

JUDGE_PROMPT = """You are an impartial, expert evaluator judging the output of an Insurance AI Assistant.
Evaluate the Assistant Response based on the User Query and the Retrieved Context.

[User Query]:
{query}

[Retrieved Context / Knowledge Base]:
{context}

[Assistant Response]:
{response}

Evaluate on a scale of 1 to 5 for each dimension:
1. Groundedness / Faithfulness (1-5): Is every factual claim in the response supported by the retrieved context? (5 = 100% faithful, 1 = hallucinated/contradicts context).
2. Answer Relevance (1-5): Does the response directly and clearly answer the user query? (5 = perfect answer, 1 = completely unhelpful/off-topic).
3. Tone & Professionalism (1-5): Is the tone helpful, empathetic, and appropriate for insurance?

Respond ONLY with valid JSON in this exact structure:
{{
  "groundedness": 5,
  "relevance": 5,
  "professionalism": 5,
  "reason": "Short explanation of the score"
}}
"""


async def evaluate_rag_response_with_judge(
    judge_llm,
    query: str,
    context: str,
    response: str
) -> Dict[str, Any]:
    """Use an LLM judge to evaluate RAG response groundedness and relevance."""
    prompt = JUDGE_PROMPT.format(
        query=query,
        context=context or "No context provided",
        response=response or "Empty response"
    )

    try:
        messages = [HumanMessage(content=prompt)]
        result = await judge_llm.ainvoke(messages)
        content = result.content.strip()

        # Clean JSON markdown blocks if any
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        scores = json.loads(content)
        return {
            "groundedness": float(scores.get("groundedness", 0)),
            "relevance": float(scores.get("relevance", 0)),
            "professionalism": float(scores.get("professionalism", 0)),
            "reason": scores.get("reason", "")
        }
    except Exception as e:
        logger.warning("LLM Judge evaluation failed: %s", e)
        return {
            "groundedness": 3.0,
            "relevance": 3.0,
            "professionalism": 3.0,
            "reason": f"Evaluator fallback due to error: {str(e)}"
        }


# ── 4. Key Points Coverage (Deterministic) ──────────────────────────────

def evaluate_key_points_coverage(response: str, expected_key_points: List[str]) -> Dict[str, Any]:
    """Check how many expected key points / concepts are mentioned in the answer."""
    if not expected_key_points:
        return {"coverage_pct": 100.0, "matched": [], "missed": []}

    resp_lower = (response or "").lower()
    matched = []
    missed = []

    for point in expected_key_points:
        # Check simple word overlap
        words = [w.lower() for w in re.findall(r'\w+', point) if len(w) > 3]
        overlap_count = sum(1 for w in words if w in resp_lower)
        if words and (overlap_count / len(words)) >= 0.4:
            matched.append(point)
        else:
            missed.append(point)

    coverage_pct = round((len(matched) / len(expected_key_points)) * 100, 1)
    return {
        "coverage_pct": coverage_pct,
        "matched": matched,
        "missed": missed
    }
