"""The single gateway for every LLM / AI call in CreatorOS.

All agents talk to the Mesh API (https://api.meshapi.ai/v1) through this module using the
OpenAI SDK pointed at Mesh's OpenAI-compatible endpoint. Nothing else in the codebase
instantiates an LLM client.

`MeshClient(mock=True)` returns deterministic canned responses. That mode exists ONLY so the
unit / integration / UI test suites can run offline and deterministically; the application
itself always runs against Mesh unless MESH_MOCK=1 is set explicitly.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from openai import OpenAI

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class LLMCall:
    """Record of one gateway call — surfaced in the decision trail and API."""

    task: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    mock: bool = False


@dataclass
class MeshClient:
    api_key: str
    base_url: str = "https://api.meshapi.ai/v1"
    chat_model: str = "openai/gpt-4o-mini"
    image_model: str = "openai/gpt-image-1"
    embedding_model: str = "openai/text-embedding-3-small"
    mock: bool = False
    timeout: float = 90.0
    calls: list[LLMCall] = field(default_factory=list)
    _client: OpenAI | None = field(default=None, repr=False)
    _mock_state: dict[str, int] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ setup
    def __post_init__(self) -> None:
        if not self.mock:
            if not self.api_key:
                raise RuntimeError(
                    "MESH_API_KEY is not set. Every LLM call must go through Mesh API — "
                    "add MESH_API_KEY=rsk_... to your .env (or set MESH_MOCK=1 for offline tests)."
                )
            # Mesh is OpenAI-compatible: one key, many models.
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)

    # ------------------------------------------------------------------- chat
    def chat(
        self,
        *,
        task: str,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.7,
        json_mode: bool = False,
        max_tokens: int = 1500,
    ) -> str:
        model = model or self.chat_model
        started = time.perf_counter()
        if self.mock:
            text = self._mock_chat(task, system, user, json_mode)
            self.calls.append(LLMCall(task=task, model=f"mock/{model}", mock=True))
            return text

        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(  # type: ignore[union-attr]
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **kwargs,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        self.calls.append(
            LLMCall(
                task=task,
                model=model,
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        return text

    def chat_json(self, **kwargs: Any) -> dict[str, Any]:
        """Chat call that must return a JSON object. Tolerates ```json fences."""
        text = self.chat(json_mode=True, **kwargs)
        return parse_json_object(text)

    # ------------------------------------------------------------------ images
    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> bytes:
        """Return PNG bytes for `prompt` from an image model reachable through Mesh."""
        if self.mock:
            self.calls.append(LLMCall(task="image", model=f"mock/{self.image_model}", mock=True))
            return _placeholder_png()
        started = time.perf_counter()
        resp = self._client.images.generate(  # type: ignore[union-attr]
            model=self.image_model, prompt=prompt, n=1, size=size
        )
        item = resp.data[0]
        if getattr(item, "b64_json", None):
            data = base64.b64decode(item.b64_json)
        elif getattr(item, "url", None):
            import httpx

            data = httpx.get(item.url, timeout=60).content
        else:  # pragma: no cover - defensive
            raise RuntimeError("Image model returned neither b64_json nor url")
        self.calls.append(
            LLMCall(task="image", model=self.image_model, latency_ms=int((time.perf_counter() - started) * 1000))
        )
        return data

    # -------------------------------------------------------------- embeddings
    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.mock:
            self.calls.append(LLMCall(task="embed", model=f"mock/{self.embedding_model}", mock=True))
            return [_hash_embedding(t) for t in texts]
        resp = self._client.embeddings.create(model=self.embedding_model, input=texts)  # type: ignore[union-attr]
        self.calls.append(LLMCall(task="embed", model=self.embedding_model))
        return [d.embedding for d in resp.data]

    # ------------------------------------------------------------- mock engine
    def _mock_chat(self, task: str, system: str, user: str, json_mode: bool) -> str:
        """Deterministic, *structurally faithful* stand-ins for each agent's output.

        They are intentionally simple; their job is to let tests exercise the orchestration,
        the editor loop (which genuinely changes the draft), the learning step and the API —
        never to stand in for the product at runtime.
        """
        n = self._mock_state.get(task, 0) + 1
        self._mock_state[task] = n
        topic = _extract(user, r"Brief:\s*(.+)") or _extract(user, r"topic[:=]\s*(.+)") or "the topic"
        platform = _extract(user, r"Platform:\s*(\w+)") or "linkedin"

        if task == "strategist":
            return json.dumps(
                {
                    "angle": f"A contrarian, practitioner-first take on {topic}",
                    "hook": f"Most teams get {topic} wrong. Here's what actually works.",
                    "hook_type": "contrarian",
                    "audience": "Engineering leaders and senior ICs",
                    "key_points": [
                        f"Why conventional advice on {topic} fails in practice",
                        "A concrete, repeatable approach that has worked",
                        "One measurable outcome to aim for this quarter",
                    ],
                    "cta": "Ask readers which approach they use",
                    "format": "short paragraphs with a list",
                    "reasoning": "Contrarian hooks have performed best for this audience; the brief is "
                    "opinion-friendly and the platform rewards a strong first line.",
                }
            )
        if task == "writer" and platform == "x":
            return json.dumps(
                {
                    "draft": f"Most teams get {topic[:60]} wrong. Measure one thing, ship small, write the decision down. Which do you skip?",
                    "hashtags": ["#Engineering"],
                    "notes": "Single post under 280 characters.",
                }
            )
        if task == "writer":
            return json.dumps(
                {
                    "draft": (
                        f"Most teams get {topic} wrong. Here's what actually works.\n\n"
                        f"Everyone talks about {topic}, but the usual advice stops at slogans. "
                        "In practice three things matter:\n\n"
                        "1. Make the goal measurable.\n2. Ship small and review often.\n3. Write the decision down.\n\n"
                        "Which of these do you already do?"
                    ),
                    "hashtags": ["#" + re.sub(r"\W", "", topic.title())[:20], "#Leadership"],
                    "notes": f"Draft written for {platform}.",
                }
            )
        if task == "writer_revise":
            prev = _extract(user, r"CURRENT DRAFT:\n(.+?)\n\nEDITOR", flags=re.S) or ""
            revised = prev.replace("Everyone talks about", "Everyone *says* they care about").rstrip()
            if platform == "x":
                revised = (revised.replace("Which do you skip?", "") .strip() + " Try it for 30 days.")[:275]
            else:
                revised += "\n\nTakeaway: pick one of the three, measure it for 30 days, and share the result."
            return json.dumps({"draft": revised, "hashtags": ["#Engineering", "#Leadership"], "change_log": [
                "Sharpened the second sentence.",
                "Added a concrete takeaway with a timeframe to satisfy the editor's specificity request.",
            ]})
        if task == "editor":
            first = n % 2 == 1  # alternate: first review requests revision, second accepts
            return json.dumps(
                {
                    "score": 6.4 if first else 8.6,
                    "criteria": {
                        "hook_strength": 7 if first else 8,
                        "clarity": 7 if first else 9,
                        "specificity": 4 if first else 8,
                        "brand_voice_fit": 7 if first else 9,
                        "platform_fit": 7 if first else 9,
                        "cta_quality": 6 if first else 8,
                    },
                    "verdict": "revise" if first else "accept",
                    "issues": ["Too generic — no concrete example or timeframe.", "Ending is weak."]
                    if first
                    else [],
                    "required_edits": [
                        "Add one concrete, time-bound takeaway.",
                        "Tighten the second sentence.",
                    ]
                    if first
                    else [],
                    "reasoning": "Specificity is the weakest criterion; the draft reads as advice without evidence."
                    if first
                    else "All criteria now at or above threshold; the revision added the missing specificity.",
                }
            )
        if task == "visual":
            return json.dumps(
                {
                    "image_prompt": f"Minimal editorial illustration about {topic}, bold geometric shapes, "
                    "deep navy and amber palette, no text",
                    "headline": f"{topic[:40]}: boring wins",
                    "subline": "Measure one thing. Ship small. Write it down.",
                    "palette": "amber",
                    "style": "editorial illustration",
                    "alt_text": f"Abstract illustration representing {topic}",
                    "reasoning": "Abstract editorial style matches a professional brand voice and avoids text artefacts.",
                }
            )
        if task == "brand_voice":
            return json.dumps(
                {
                    "tone": "direct, practical, lightly opinionated",
                    "persona": "Senior engineer who has shipped the thing and tells you what broke",
                    "sentence_style": "short declarative sentences; occasional one-line paragraphs",
                    "vocabulary": ["ship", "in practice", "measure", "trade-off"],
                    "signature_moves": ["opens with a contrarian claim", "ends with a question"],
                    "do": ["use concrete numbers", "name the trade-off"],
                    "dont": ["no buzzword stacking", "no exclamation marks"],
                    "emoji_usage": "none",
                    "formatting": "numbered lists for steps",
                    "summary": "Direct, practitioner voice with contrarian openers and concrete takeaways.",
                }
            )
        if task == "learner":
            return json.dumps(
                {
                    "insights": [
                        {
                            "insight": "Contrarian hooks out-perform question hooks for this audience.",
                            "rule": "Prefer a contrarian or bold-claim opening line.",
                            "confidence": 0.7,
                            "applies_to": "hook",
                        },
                        {
                            "insight": "Posts with a concrete time-bound takeaway earn more comments.",
                            "rule": "End with one specific, time-bound action.",
                            "confidence": 0.6,
                            "applies_to": "cta",
                        },
                    ],
                    "reasoning": "Top-quartile pieces share a contrarian opener and a specific CTA; bottom-quartile pieces are generic.",
                }
            )
        if task == "judge":
            draft = _extract(user, r"CONTENT:\n(.+)", flags=re.S) or user
            specificity = 8 if re.search(r"\d", draft) else 4
            return json.dumps(
                {
                    "hook_strength": 7,
                    "clarity": 8,
                    "specificity": specificity,
                    "brand_voice_fit": 8,
                    "platform_fit": 8,
                    "cta_quality": 8 if "Takeaway" in draft else 5,
                    "reasoning": "Mock judge: specificity and CTA scored from concrete markers in the text.",
                }
            )
        if task == "adapt":
            return json.dumps({"draft": f"[{platform}] " + (_extract(user, r"SOURCE CONTENT:\n(.+)", flags=re.S) or "")[:260], "hashtags": ["#AI"]})
        return json.dumps({"result": f"mock response for {task}"}) if json_mode else f"mock response for {task}"


# ---------------------------------------------------------------------- helpers
def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _extract(text: str, pattern: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _hash_embedding(text: str, dim: int = 64) -> list[float]:
    """Cheap bag-of-words hashed embedding so mock cosine similarity still reflects word overlap."""
    vec = [0.0] * dim
    for tok in re.findall(r"[a-z]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _placeholder_png() -> bytes:
    return _PLACEHOLDER_PNG


@lru_cache
def get_mesh_client() -> MeshClient:
    s = get_settings()
    return MeshClient(
        api_key=s.mesh_api_key,
        base_url=s.mesh_base_url,
        chat_model=s.mesh_chat_model,
        image_model=s.mesh_image_model,
        embedding_model=s.mesh_embedding_model,
        mock=s.mesh_mock,
        timeout=s.mesh_timeout_seconds,
    )
