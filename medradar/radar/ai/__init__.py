"""Optional local small-model enrichment: backlog, one-shot worker, measured evaluation.

Nothing in this package is on the critical path of discovery. Import errors, a missing model,
a slow host or a wrong answer all degrade to "the backlog grew", never to "the radar stopped".
"""

from __future__ import annotations

from .prompts import PROMPT_VERSION, build_messages, build_prompt, extract_json
from .worker import (
    DEFAULT_MODEL,
    MODEL_VERSION_TAG,
    AIUnavailable,
    QwenClassifier,
    default_model_path,
    run_batch,
)

__all__ = [
    "AIUnavailable",
    "DEFAULT_MODEL",
    "MODEL_VERSION_TAG",
    "PROMPT_VERSION",
    "QwenClassifier",
    "build_messages",
    "build_prompt",
    "default_model_path",
    "extract_json",
    "run_batch",
]
