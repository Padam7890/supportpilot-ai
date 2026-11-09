"""Send a minimal synthetic completion from the current runtime."""

import argparse
import asyncio
import json
from contextlib import aclosing

from app.features.ai.infrastructure.llm_gateway import (
    AIProviderError,
    CompletionEnd,
    generate_completion,
    stream_completion,
)


async def check_provider(*, streaming: bool) -> int:
    messages = [{"role": "user", "content": "Reply with OK."}]
    try:
        if streaming:
            async with aclosing(stream_completion(messages, max_tokens=64)) as events:
                async for event in events:
                    if isinstance(event, CompletionEnd):
                        break
        else:
            await generate_completion(messages, max_tokens=64)
    except AIProviderError as error:
        print(json.dumps({
            "ok": False,
            "streaming": streaming,
            "error_code": error.code,
            "provider_http_status": error.http_status,
            "provider_reason": error.provider_reason,
        }))
        return 1
    print(json.dumps({"ok": True, "streaming": streaming}))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stream", action="store_true")
    raise SystemExit(asyncio.run(check_provider(streaming=parser.parse_args().stream)))
