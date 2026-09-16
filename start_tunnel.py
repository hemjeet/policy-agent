"""Start an ngrok tunnel to expose the MCP server over HTTPS."""
from pyngrok import ngrok

def main():
    public_url = ngrok.connect(8001, "http")
    print(f"\n{'='*60}")
    print(f"  MCP server accessible at: {public_url}")
    print(f"  Claude Desktop URL: {public_url}/sse")
    print(f"{'='*60}")
    print("Press Ctrl+C to stop\n")

    try:
        while True:
            pass
    except KeyboardInterrupt:
        ngrok.kill()
        print("Tunnel closed.")

if __name__ == "__main__":
    main()
