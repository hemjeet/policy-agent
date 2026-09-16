"""
Policy Agent — MCP Server

A single-file MCP server that wraps the policy-agent tools for use by
any MCP-compatible client (Claude Desktop, Antigravity, etc.).

Supports both transports:
  - stdio  : python mcp_server.py                   (for Claude Desktop)
  - sse    : python mcp_server.py --transport sse    (for remote clients)
"""

import os
import sys
import logging

# ── Project root setup (so imports work from any working directory)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# ── Suppress FastMCP banner
os.environ["FASTMCP_SHOW_SERVER_BANNER"] = "false"

# ── Logging to file (keeps stdout/stderr clean for stdio transport)
logging.basicConfig(
    filename=os.path.join(PROJECT_ROOT, "mcp_server.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

# ── Load env vars
from dotenv import load_dotenv
load_dotenv()

# ── Initialize vectorstore
from agent.vectorstore import init_vectorstore
init_vectorstore()

# ── FastMCP server
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("policy-agent")



# ─── Tools ────────────────────────────────────────────────────────────


@mcp.tool()
def check_claim_status_tool(phone_number: str) -> str:
    """Look up all claims for a customer by their registered phone number.
    Returns claim details and full status-change history.
    """
    from tools.check_claim_status import check_claim_status
    logger.info("MCP → check_claim_status(phone_number=%s)", phone_number)
    return check_claim_status.invoke({"phone_number": phone_number})


@mcp.tool()
def get_customer_info_tool(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> str:
    """Look up customer profile information.
    Retrieves name, contact details, address, and summary counts.
    At least one of email, phone, or customer_id must be provided.
    """
    from tools.get_customer_info import get_customer_info
    logger.info("MCP → get_customer_info(email=%s, phone=%s, id=%s)", email, phone, customer_id)
    return get_customer_info.invoke({
        "email": email,
        "phone": phone,
        "customer_id": customer_id,
    })


@mcp.tool()
def get_policy_info_tool(
    policy_number: Optional[str] = None,
    customer_email: Optional[str] = None,
    customer_phone: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> str:
    """Look up policy details including coverage, premiums, deductibles,
    validity dates, and active claims.
    Provide at least policy_number, customer_email, or customer_phone.
    """
    from tools.get_policy_info import get_policy_info
    logger.info("MCP → get_policy_info(policy=%s, email=%s, phone=%s)", policy_number, customer_email, customer_phone)
    return get_policy_info.invoke({
        "policy_number": policy_number,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "status_filter": status_filter,
    })


@mcp.tool()
async def search_knowledge_base_tool(query: str, top_k: int = 3) -> str:
    """Semantic search over the insurance policy handbook and knowledge base.
    Use for general, how-to, or policy questions.
    """
    from tools.search_knowledge_base import search_knowledge_base
    from agent import vectorstore as vs_module
    logger.info("MCP → search_knowledge_base(query=%s, top_k=%s)", query, top_k)
    config = {"configurable": {"vectorstore": vs_module.vectorstore}}
    return await search_knowledge_base.ainvoke({"query": query, "top_k": top_k}, config=config)


# ─── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Policy Agent MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse", "http"], default="http",
        help="Transport type (default: http)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="Port (default: 8001)")
    args = parser.parse_args()

    mcp.run(transport=args.transport, host=args.host, port=args.port)
