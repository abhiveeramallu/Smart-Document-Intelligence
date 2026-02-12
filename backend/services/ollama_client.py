from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class OllamaConfig:
    base_url: str
    model: str
    vision_model: str = ""


class OllamaClient:
    def __init__(self, config: OllamaConfig, timeout_seconds: float = 120.0) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.get(f"{self.config.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # pragma: no cover - depends on local Ollama runtime
            return {
                "available": False,
                "error": str(exc),
                "model": self.config.model,
                "vision_model": self.config.vision_model,
            }

        model_names = [item.get("name", "") for item in payload.get("models", [])]
        return {
            "available": True,
            "error": "",
            "model": self.config.model,
            "vision_model": self.config.vision_model,
            "installed_models": model_names,
        }

    def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.config.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        stripped = (content or "").strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            stripped = stripped.replace("json\n", "", 1).strip()

        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"raw": content}

    def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.1,
        images: list[bytes] | None = None,
    ) -> dict[str, Any]:
        selected_model = model or self.config.model
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        user_message: dict[str, Any] = {"role": "user", "content": user_prompt}
        if images:
            user_message["images"] = [base64.b64encode(item).decode("utf-8") for item in images]
        messages.append(user_message)

        payload = {
            "model": selected_model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }

        response = self._chat(payload)
        content = response.get("message", {}).get("content", "")
        parsed = self._parse_json_content(content)
        parsed.setdefault("_model", selected_model)
        return parsed

    def chat_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        selected_model = model or self.config.model
        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        response = self._chat(payload)
        return response.get("message", {}).get("content", "").strip()
