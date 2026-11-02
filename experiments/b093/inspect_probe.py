"""Report the content types recorded by the external probe (HTTP 200 is not the same as usable data)."""
from __future__ import annotations

import json
from pathlib import Path

payload = json.loads(Path("research/studies/early_signal_5firms/EXTERNAL_SOURCE_PROBE.json")
                     .read_text(encoding="utf-8"))
for name, block in payload["results"].items():
    content_type = str(block.get("content_type"))[:50]
    print(f"{name:26s} status={block['status']} reachable={block['reachable']} ctype={content_type}")
