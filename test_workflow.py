"""
Verification script for the Insurance Policy Agent workflow.

This script tests the LangGraph agent state machine, including the
router LLM, the knowledge base search, and the transactional database tools.
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.messages import HumanMessage
from agent import PolicyAgent
from agent.config import LLM, LLM_PROVIDER, TOOLS

DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION_NAME = "insurance_knowledge_base"


def print_step_header(title: str):
    print("\n" + "=" * 80)
    print(f" {title.upper()} ".center(80, "="))
    print("=" * 80 + "\n")


def print_agent_messages(state: dict):
    print("Conversation Timeline:")
    print("-" * 50)
    for msg in state.get("messages", []):
        role = msg.__class__.__name__.replace("Message", "")
        content = msg.content
        # Truncate content for display if too long
        if len(content) > 300:
            content = content[:300] + "...\n[Content Truncated]"
        print(f"[{role}]: {content}")
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            print(f"  Tool Calls: {msg.tool_calls}")
    print("-" * 50)
    print(f"State variables:")
    print(f"  - Intent classified: {state.get('intent')}")
    print(f"  - Phone number: {state.get('phone_number')}")
    print(f"  - Iteration count: {state.get('iteration_count')}")
    print("=" * 80 + "\n")


def main():
    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set in .env")
        sys.exit(1)

    # 1. Initialize LLM
    logger.info(f"Initializing LLM using provider: {LLM_PROVIDER}")
    if LLM_PROVIDER == "deepseek":
        llm = ChatOpenAI(
            model=LLM["model"],
            openai_api_key=LLM["api_key"],
            openai_api_base=LLM["base_url"],
            temperature=0,
        )
    else:
        llm = ChatOpenAI(
            model=LLM["model"],
            openai_api_key=LLM["api_key"],
            temperature=0,
        )

    # 2. Initialize Embeddings & PGVector Store
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=DATABASE_URL,
        use_jsonb=True,
    )

    # 3. Initialize Agent
    agent = PolicyAgent(router_llm= llm, llm=llm, tools=TOOLS)

    # Set up runtime configuration (passing vectorstore via config for tools)
    config = {
        "configurable": {
            "thread_id": "test_session_1",
            "vectorstore": vectorstore,
        }
    }

    # =========================================================================
    # Test Scenario 1: Knowledge Base Routing
    # =========================================================================
    print_step_header("Scenario 1: General Knowledge Base Question")
    
    query1 = "How do I file a claim with SecureLife?"
    logger.info(f"User Query: '{query1}'")
    
    initial_state = {
        "messages": [HumanMessage(content=query1)],
    }
    
    # Run the graph
    result = agent.graph.invoke(initial_state, config=config)
    print_agent_messages(result)

    # =========================================================================
    # Test Scenario 2: Transactional Claim Check Routing
    # =========================================================================
    print_step_header("Scenario 2: Transactional Query (Claims Check)")
    
    # Let's start a fresh session thread for thread isolation
    config2 = {
        "configurable": {
            "thread_id": "test_session_2",
            "vectorstore": vectorstore,
        }
    }
    
    query2 = "What is the status of my claims? My registered phone number is +91-9876543210."
    logger.info(f"User Query: '{query2}'")
    
    initial_state2 = {
        "messages": [HumanMessage(content=query2)],
    }
    
    # Run the graph
    result2 = agent.graph.invoke(initial_state2, config=config2)
    print_agent_messages(result2)


if __name__ == "__main__":
    main()
