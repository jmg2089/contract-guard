"""LLM 호출 추상화.

- dummy       : 키 없이도 파이프라인 전체가 돌아간다. 금요일 밤 병렬 작업의 전제.
- openai_compatible : OpenAI, Upstage(Solar), Groq, Together 등 /v1 호환 엔드포인트 전부
- anthropic   : Claude

공급자를 바꿔도 judge.py는 한 줄도 안 바뀐다.
"""
import json
import re

from config import LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL, LLM_API_KEY, LLM_TIMEOUT


class LLMError(RuntimeError):
    pass


def _dummy(system: str, user: str) -> str:
    """LLM 없이도 형식이 맞는 응답을 돌려준다. 판정은 전부 ok."""
    return json.dumps({"verdict": "ok", "law_id": "", "quote": "", "reason": "dummy 모드", "suggestion": ""}, ensure_ascii=False)


def _openai_compatible(system: str, user: str) -> str:
    from openai import OpenAI

    kwargs = {"api_key": LLM_API_KEY or "sk-none"}
    if LLM_BASE_URL:
        kwargs["base_url"] = LLM_BASE_URL
    client = OpenAI(**kwargs)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        timeout=LLM_TIMEOUT,
    )
    return resp.choices[0].message.content or ""


def _anthropic(system: str, user: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=LLM_API_KEY)
    resp = client.messages.create(
        model=LLM_MODEL,
        max_tokens=1024,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


_PROVIDERS = {
    "dummy": _dummy,
    "openai_compatible": _openai_compatible,
    "anthropic": _anthropic,
}


def complete(system: str, user: str) -> str:
    fn = _PROVIDERS.get(LLM_PROVIDER)
    if fn is None:
        raise LLMError(f"알 수 없는 LLM_PROVIDER: {LLM_PROVIDER}")
    return fn(system, user)


def parse_json(raw: str) -> dict:
    """모델이 코드펜스나 잡담을 섞어 내보내도 첫 JSON 객체를 건져낸다."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    depth, start = 0, -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    start = -1
    return {}
