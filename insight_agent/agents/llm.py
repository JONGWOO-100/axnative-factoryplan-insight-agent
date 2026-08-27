"""LLM 프로바이더 추상화 -- Claude Code(Anthropic)/Codex(OpenAI) 양쪽 런타임에서
동작하도록 환경변수로 설정된 키를 자동 선택한다.

이 프로젝트는 키가 없어도 항상 끝까지 동작해야 한다는 불변식(narrative.py의 원래
설계)을 그대로 지킨다 -- 그래서 여기서는 예외를 삼키지 않고 그대로 올린다.
호출부(narrative.py, chat/engine.py)가 `available()`로 먼저 확인하거나
try/except로 감싸 결정론적 템플릿 경로로 넘어가야 한다.
"""
from __future__ import annotations

import os
from typing import Optional


class LlmUnavailable(RuntimeError):
    pass


def active_provider() -> Optional[str]:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return None


def available() -> bool:
    return active_provider() is not None


def generate(prompt: str, system: Optional[str] = None, max_tokens: int = 500) -> str:
    provider = active_provider()
    if provider == "anthropic":
        return _generate_anthropic(prompt, system, max_tokens)
    if provider == "openai":
        return _generate_openai(prompt, system, max_tokens)
    raise LlmUnavailable("ANTHROPIC_API_KEY / OPENAI_API_KEY 중 아무것도 설정되어 있지 않습니다.")


def _generate_anthropic(prompt: str, system: Optional[str], max_tokens: int) -> str:
    import anthropic  # 키가 없을 때는 이 의존성 자체가 필요 없도록 지연 임포트

    client = anthropic.Anthropic()
    kwargs = {"system": system} if system else {}
    message = client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return message.content[0].text


def _generate_openai(prompt: str, system: Optional[str], max_tokens: int) -> str:
    import openai  # Codex/OpenAI 런타임에서만 필요한 지연 임포트

    client = openai.OpenAI()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content
