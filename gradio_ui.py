"""
Gradio chat UI for the Policy Agent — with OTP-based phone authentication.

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
.login-container { max-width: 400px; margin: 2em auto; }
.otp-status { padding: 0.5em; border-radius: 0.5em; text-align: center; }
"""


def create_demo(api_base: str = "http://localhost:8000"):
    """Build and return a Gradio Blocks app with OTP login + chat."""

    # ── Chat helpers ──────────────────────────────────────────────────

    async def _stream_chat(message: str, thread_id: str, token: str):
        full_response = ""
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{api_base}/chat/stream",
                json={"message": message, "thread_id": thread_id},
                headers=headers,
            ) as resp:
                if resp.status_code == 401:
                    yield "[Session expired. Please log in again.]"
                    return
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

    async def _batch_chat(message: str, thread_id: str, token: str):
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{api_base}/chat",
                json={"message": message, "thread_id": thread_id},
                headers=headers,
            )
            if resp.status_code == 401:
                return "[Session expired. Please log in again.]", thread_id
            resp.raise_for_status()
            data = resp.json()
        return data["response"], data.get("thread_id", thread_id)

    # ── Auth helpers ──────────────────────────────────────────────────

    async def send_otp(phone: str):
        """Request an OTP for the given phone number."""
        if not phone or not phone.strip():
            return "⚠️ Please enter your phone number.", "", gr.update(), gr.update()
        phone = phone.strip()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{api_base}/auth/send-otp",
                    json={"phone": phone},
                )
                if resp.status_code == 404:
                    return "❌ No customer found with this phone number.", "", gr.update(), gr.update()
                if resp.status_code == 429:
                    return "⚠️ Too many attempts. Please wait a minute.", "", gr.update(), gr.update()
                resp.raise_for_status()
                data = resp.json()
                demo_otp = data.get("demo_otp", "")
                return (
                    f"✅ OTP sent! (Demo OTP: **{demo_otp}**)",
                    "",
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                )
        except httpx.ConnectError:
            return f"❌ Cannot connect to API at `{api_base}`.", "", gr.update(), gr.update()
        except Exception as e:
            return f"❌ Error: {str(e)}", "", gr.update(), gr.update()

    async def verify_and_login(phone: str, otp: str):
        """Verify OTP and return the auth token + customer name."""
        if not otp or not otp.strip():
            return "⚠️ Please enter the OTP.", None, None, gr.update(visible=True), gr.update(visible=False), []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{api_base}/auth/verify-otp",
                    json={"phone": phone.strip(), "otp": otp.strip()},
                )
                if resp.status_code == 401:
                    return "❌ Invalid or expired OTP. Try again.", None, None, gr.update(visible=True), gr.update(visible=False), []
                if resp.status_code == 429:
                    return "⚠️ Too many attempts. Please wait.", None, None, gr.update(visible=True), gr.update(visible=False), []
                resp.raise_for_status()
                data = resp.json()
                token = data["access_token"]
                name = data["customer_name"]
                return (
                    f"✅ Welcome, **{name}**!",
                    token,
                    name,
                    gr.update(visible=False),  # hide login
                    gr.update(visible=True),   # show chat
                    [{"role": "assistant", "content": f"Hi **{name}**, how may I help you today?"}],
                )
        except Exception as e:
            return f"❌ Error: {str(e)}", None, None, gr.update(visible=True), gr.update(visible=False), []

    def logout():
        """Clear session and show login screen."""
        return (
            None,   # token
            None,   # customer_name
            [],     # chatbot
            None,   # thread_state
            "",     # phone
            "",     # otp
            "",     # status
            gr.update(visible=True),   # login
            gr.update(visible=False),  # chat
        )

    # ── Chat handler ──────────────────────────────────────────────────

    async def respond(history, thread_id, use_stream, token):
        if not history:
            return
        if not token:
            history.append({"role": "assistant", "content": "⚠️ Session expired. Please log in again."})
            yield history, thread_id
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
                async for partial in _stream_chat(user_message, tid, token):
                    messages[-1] = {"role": "assistant", "content": partial}
                    yield list(messages), tid
            else:
                answer, tid = await _batch_chat(user_message, tid, token)
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

    # ── Build UI ──────────────────────────────────────────────────────

    with gr.Blocks(
        title="SecureLife Insurance — Policy Agent",
        css=CUSTOM_CSS,
        theme=gr.themes.Soft(primary_hue="blue"),
    ) as demo:
        # Session state
        token_state = gr.State(None)
        customer_name_state = gr.State(None)
        thread_state = gr.State(None)

        gr.HTML(
            """
            <div class="policy-header">
              <h1>SecureLife Insurance</h1>
              <p>Policy Agent — ask anything about claims, policies, coverage, and more</p>
            </div>
            """
        )

        # ── Login Section ─────────────────────────────────────────────
        with gr.Column(visible=True, elem_classes="login-container") as login_section:
            gr.Markdown("### 🔐 Login with your registered phone number")
            phone_input = gr.Textbox(
                placeholder="+91-9876543210",
                label="Phone Number",
                scale=1,
            )
            send_otp_btn = gr.Button("Send OTP", variant="primary")
            otp_input = gr.Textbox(
                placeholder="Enter 6-digit OTP",
                label="OTP",
                interactive=False,
            )
            verify_btn = gr.Button("Verify & Login", variant="primary", interactive=False)
            login_status = gr.Markdown("")

        # ── Chat Section (hidden until login) ─────────────────────────
        with gr.Column(visible=False) as chat_section:
            chatbot = gr.Chatbot(
                label="Policy Agent",
                placeholder="<strong>You're logged in!</strong> Ask about your claims, policies, or coverage.",
                height=520,
                type="messages",
                show_copy_button=True,
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
                logout_btn = gr.Button("Logout", variant="stop", scale=1)

        # ── Event wiring: Login ───────────────────────────────────────
        send_otp_btn.click(
            fn=send_otp,
            inputs=[phone_input],
            outputs=[login_status, otp_input, otp_input, verify_btn],
        )

        verify_btn.click(
            fn=verify_and_login,
            inputs=[phone_input, otp_input],
            outputs=[login_status, token_state, customer_name_state, login_section, chat_section, chatbot],
        )

        # ── Event wiring: Chat ────────────────────────────────────────
        msg.submit(
            fn=lambda m, h: ((h or []) + [{"role": "user", "content": m}], ""),
            inputs=[msg, chatbot],
            outputs=[chatbot, msg],
            queue=False,
        ).then(
            fn=respond,
            inputs=[chatbot, thread_state, stream_toggle, token_state],
            outputs=[chatbot, thread_state],
        )

        clear_btn.click(
            fn=lambda: ([], None),
            outputs=[chatbot, thread_state],
        )

        logout_btn.click(
            fn=logout,
            outputs=[
                token_state, customer_name_state, chatbot, thread_state,
                phone_input, otp_input, login_status,
                login_section, chat_section,
            ],
        )

    return demo


if __name__ == "__main__":
    demo = create_demo()
    demo.queue(default_concurrency_limit=5).launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
    )
