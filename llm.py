import json
import os

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "800"))
_client = None

TOOLS = [
    {
        "name": "get_queue_status",
        "description": "Get people ahead and estimated wait for a token number.",
        "input_schema": {
            "type": "object",
            "properties": {"token_no": {"type": "integer"}},
            "required": ["token_no"],
        },
    },
    {
        "name": "book_token",
        "description": "Book a new queue token for a user at a counter.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "counter": {"type": "string"}},
            "required": ["name", "counter"],
        },
    },
]


def _get_services():
    global _client
    try:
        import anthropic
        from rag import retrieve
        from tools import get_queue_status, book_token

        if _client is None:
            _client = anthropic.Anthropic()
        return _client, retrieve, {"get_queue_status": get_queue_status, "book_token": book_token}
    except Exception as exc:
        raise RuntimeError(f"AI service unavailable: {exc}") from exc


def chat(user_msg: str, history: list):
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "The AI chat service is not configured. Queue booking and status endpoints remain available."

    client, retrieve, funcs = _get_services()
    ctx = retrieve(user_msg)
    context_block = "\n\n".join(f"[{c['source']}] {c['text']}" for c in ctx)
    system = (
        "You are Smart Queue Buddy, a calm and helpful multilingual public-service assistant. "
        "Reply in the same language as the user's latest message. "
        "Use simple, polite, concise language and numbered steps when explaining procedures. "
        "Answer only from the verified context below and cite the source file in brackets. "
        "If information is missing, say that you do not have it and suggest asking the relevant counter. "
        "Use tools for token booking and queue status. Never invent token numbers, fees, timings, or documents.\n\n"
        f"CONTEXT:\n{context_block}"
    )
    messages = history + [{"role": "user", "content": user_msg}]

    while True:
        resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system, tools=TOOLS, messages=messages)
        if resp.stop_reason != "tool_use":
            return "".join(block.text for block in resp.content if block.type == "text")

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                out = funcs[block.name](**block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})