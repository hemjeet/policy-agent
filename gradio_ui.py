"""
Gradio chat UI for the Policy Agent — calls FastAPI /chat and /chat/stream endpoints.

Can run standalone or be mounted inside FastAPI via gr.mount_gradio_app().
"""

import json
import uuid
import httpx
import gradio as gr

TIMEOUT = 120

CUSTOM_CSS = """
.policy-header { text-align: center; margin-bottom: 0.5em; }
.policy-header h1 { margin: 0; color: #1a56db; }
.policy-header p  { margin: 0; color: #6b7280; }
footer { display: none !important; }
"""


def create_demo(api_base: str = "http://localhost:8000"):
    """Build and return a Gradio Blocks app configured for the given API base URL."""

    async def _stream_chat(message: str, thread_id: str):
        full_response = ""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{api_base}/chat/stream",
                json={"message": message, "thread_id": thread_id},
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        if "error" in chunk:
                            yield f"[Error: {chunk['error']}]"
                            return
                        content = chunk.get("content", "")
                        full_response += content
                        yield full_response
                    except json.JSONDecodeError:
                        pass

    async def _batch_chat(message: str, thread_id: str):
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{api_base}/chat",
                json={"message": message, "thread_id": thread_id},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["response"], data.get("thread_id", thread_id)

    async def respond(
        history: list[dict],
        thread_id: str | None,
        use_stream: bool,
    ):
        if not history:
            return

        messages = list(history)
        raw_content = messages[-1]["content"]
        if isinstance(raw_content, str):
            user_message = raw_content
        elif isinstance(raw_content, list) and raw_content:
            user_message = raw_content[0].get("text", str(raw_content[0]))
        else:
            user_message = str(raw_content)
        tid = thread_id or str(uuid.uuid4())

        try:
            if use_stream:
                messages.append({"role": "assistant", "content": ""})
                async for partial in _stream_chat(user_message, tid):
                    messages[-1] = {"role": "assistant", "content": partial}
                    yield list(messages), tid
            else:
                answer, tid = await _batch_chat(user_message, tid)
                messages.append({"role": "assistant", "content": answer})
                yield messages, tid
        except httpx.HTTPStatusError as e:
            messages.append({"role": "assistant", "content": (
                f"**API Error ({e.response.status_code})**: {e.response.text[:300]}"
            )})
            yield messages, tid
        except httpx.ConnectError:
            messages.append({"role": "assistant", "content": (
                f"Could not connect to the API at `{api_base}`.\n\n"
                "Make sure the FastAPI server is running."
            )})
            yield messages, tid
        except Exception as e:
            messages.append({"role": "assistant", "content": f"**Unexpected error**: {str(e)}"})
            yield messages, tid

    with gr.Blocks(
        title="SecureLife Insurance — Policy Agent",
        css=CUSTOM_CSS,
    ) as demo:
        thread_state = gr.State(None)

        gr.HTML(
            """
            <div class="policy-header">
              <h1>SecureLife Insurance</h1>
              <p>Policy Agent — ask anything about claims, policies, coverage, and more</p>
            </div>
            """
        )

        chatbot = gr.Chatbot(
            label="Policy Agent",
            placeholder="<strong>Examples:</strong><br>"
            "&bull; &nbsp;<em>How do I file a health insurance claim?</em><br>"
            "&bull; &nbsp;<em>What is No Claim Bonus?</em><br>"
            "&bull; &nbsp;<em>Is my health insurance premium tax deductible?</em><br>"
            "&bull; &nbsp;<em>What documents do I need for a motor claim?</em>",
            height=520,
            buttons=["copy"],
        )

        with gr.Row():
            msg = gr.Textbox(
                placeholder="Type your question here…",
                label="Message",
                scale=8,
                show_label=False,
            )

        with gr.Row():
            stream_toggle = gr.Checkbox(
                label="Stream response", value=True, scale=1
            )
            clear_btn = gr.Button("New Chat", variant="secondary", scale=1)

        msg.submit(
            fn=lambda m, h: ((h or []) + [{"role": "user", "content": m}], ""),
            inputs=[msg, chatbot],
            outputs=[chatbot, msg],
            queue=False,
        ).then(
            fn=respond,
            inputs=[chatbot, thread_state, stream_toggle],
            outputs=[chatbot, thread_state],
        )

        clear_btn.click(
            fn=lambda: ([], None),
            outputs=[chatbot, thread_state],
        )

    return demo


if __name__ == "__main__":
    demo = create_demo()
    demo.queue(default_concurrency_limit=5).launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        css=CUSTOM_CSS,
        theme=gr.themes.Soft(primary_hue="blue"),
    )
