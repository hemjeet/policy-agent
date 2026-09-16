import anthropic
import os
from dotenv import load_dotenv
load_dotenv()

url = "https://ferret-fabric-buddhism.ngrok-free.dev"  # ngrok tunnel to localhost:8001

client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
response = client.beta.messages.create(
    model="claude-sonnet-5",
    max_tokens=1000,
    betas=["mcp-client-2025-11-20"],
    messages=[{"role": "user", "content": "Check claim status for +91-9876543210"}],
    mcp_servers=[
        {
            "type": "url",
            "url": f"{url}/mcp/",
            "name": "policy-agent",
        }
    ],
    tools=[{"type": "mcp_toolset", "mcp_server_name": "policy-agent"}],
)
print(response.content)
