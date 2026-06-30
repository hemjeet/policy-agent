from typing import TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class PolicyAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    phone_number: str
    email: str
    customer_id: str
    policy_id: str
    claim_id: str
    iteration_count: int
    intent: str
    cached_hit: bool

    