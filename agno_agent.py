import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from langgraph.checkpoint.memory import MemorySaver
from agno.agents.langgraph import LangGraphAgent
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_deepseek import ChatDeepSeek
from agno.db.sqlite import SqliteDb
from agno.os import AgentOS
from agent import PolicyAgentV2
from agent.config import TOOLS
logger = logging.getLogger(__name__)



def _build_llm():
    from langchain_deepseek import ChatDeepSeek

    primary = ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )

    fallback = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    router = ChatOpenAI(
        model=os.getenv("ROUTER_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
        cache=True,
    )
    llm = primary.with_fallbacks([fallback])
    logger.info("  [ OK ] DeepSeek LLM loaded (%s)", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    logger.info("  [ OK ] OpenAI fallback loaded (%s)", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    logger.info("  [ OK ] Router LLM loaded (%s)", router.model_name)
    return llm, router

llm, router_llm = _build_llm()
checkpointer = MemorySaver()
# Build your existing agent
policy_agent = PolicyAgentV2(
    router_llm=router_llm,
    llm=llm,
    checkpointer=checkpointer,
    tools=TOOLS,
)

# Wrap compiled graph
agent = LangGraphAgent(
    name="Policy Agent",
    graph=policy_agent.graph,
    input_key="messages",
    output_key="messages",
)

# Serve via AgentOS
agent_os = AgentOS(
    agents=[agent],
    tracing=True,
    db=SqliteDb(db_file="tmp/agentos.db"),
)
app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(app="agno_agent:app", reload=True)

