"""Token Factory client: OpenAI-style chat calls, text or image."""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


def _load_env() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()
BASE = os.environ.get("TOKENFACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1/").rstrip("/")
KEY = os.environ.get("TOKENFACTORY_API_KEY", "")
VISION_MODEL = os.environ.get("VISION_MODEL", "nvidia/Nemotron-3.5-Super-VL")
VISION_FALLBACK = os.environ.get("VISION_FALLBACK", "zai-org/GLM-5.3-Flash")
TEXT_MODEL = os.environ.get("TEXT_MODEL", "nvidia/nemotron-3-super-120b-a12b")


def chat(model: str, content, max_tokens: int = 2000, temperature: float = 0.0, timeout: int = 25,
         extra: dict | None = None) -> str:
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
        **(extra or {}),
    }
    req = urllib.request.Request(
        f"{BASE}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.load(r)
            return d["choices"][0]["message"]["content"] or ""
        except TimeoutError as e:  # a slow model stays slow: don't burn the demo retrying it
            raise RuntimeError(f"Token Factory timed out after {timeout}s for {model}") from e
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), TimeoutError):
                raise RuntimeError(f"Token Factory timed out after {timeout}s for {model}") from e
            last = e
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Token Factory call failed for {model}: {last}")


def image_part(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b}"}}


def parse_json(text: str):
    """Pull the first JSON object or array out of a model reply (handles code fences)."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No JSON in model reply: {text[:200]!r}")
