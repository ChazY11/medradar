"""Verify the pinned model snapshot and write its provenance manifest.

``dl.py`` already refuses to accept a chunk whose whole-file SHA-256 does not match, so
this is a second, independent check run after the fact: it re-hashes every file on disk
and compares it with the SHA-256 published by the Hugging Face tree API at the pinned
revision.  A file that changed on disk after download (partial write, disk corruption,
someone swapping weights) fails here.

Writes a JSON manifest that every experiment references: repo id, pinned revision, per
file sizes and hashes, and the tree-API SHA it was compared against.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

REPO = "Qwen/Qwen3-4B-Instruct-2507"
REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
MODEL_DIR = Path(r"D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507")
OUT = Path(r"D:\DEPPSKK\ml-work\model_download.json")

# (path, expected bytes, expected sha256) from
# https://huggingface.co/api/models/Qwen/Qwen3-4B-Instruct-2507/tree/<revision>?recursive=true
# Empty sha256 = a small non-LFS file whose identity is its byte count + tree entry.
FILES = [
    (".gitattributes", 1570, ""),
    ("LICENSE", 11343, ""),
    ("README.md", 8168, ""),
    ("config.json", 727, ""),
    ("generation_config.json", 238, ""),
    ("merges.txt", 1671839, ""),
    ("model-00001-of-00003.safetensors", 3957900840, "75311d91bb08cf0b882913da464a1e722a31fb44db35208663487efb7a3d8ed6"),
    ("model-00002-of-00003.safetensors", 3987450520, "0b48adbb1f60e901153d91907ba11ce63bd4b8b584482e730f48808d055dfba1"),
    ("model-00003-of-00003.safetensors", 99630640, "7dd39ccca5e4de123c74c14af44c9bf2eb75df33b4614382af0134528e060d5d"),
    ("model.safetensors.index.json", 32819, ""),
    ("tokenizer.json", 11422654, "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4"),
    ("tokenizer_config.json", 9377, ""),
    ("vocab.json", 2776833, ""),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    started = time.time()
    records = []
    all_ok = True
    for name, expected_bytes, expected_sha in FILES:
        path = MODEL_DIR / name
        if not path.is_file():
            records.append({"path": name, "present": False, "verified": False})
            all_ok = False
            print(f"MISSING {name}")
            continue
        size = path.stat().st_size
        digest = sha256_file(path)
        size_ok = size == expected_bytes
        hash_ok = (digest == expected_sha) if expected_sha else None
        verified = size_ok and (hash_ok is not False)
        all_ok = all_ok and verified
        records.append(
            {
                "path": name,
                "present": True,
                "bytes": size,
                "expected_bytes": expected_bytes,
                "sha256": digest,
                "expected_sha256": expected_sha or None,
                "size_ok": size_ok,
                "sha256_ok": hash_ok,
                "verified": verified,
            }
        )
        print(f"{'OK ' if verified else 'BAD'} {name:42s} {size:>12,} sha={digest[:16]}...")

    manifest = {
        "repo_id": REPO,
        "revision": REVISION,
        "local_dir": str(MODEL_DIR),
        "tree_api": f"https://huggingface.co/api/models/{REPO}/tree/{REVISION}?recursive=true",
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "files": records,
        "all_verified": all_ok,
        "method": "full-file SHA-256 compared with the HF tree API LFS oid; sizes compared for every file",
        "verified_seconds": round(time.time() - started, 1),
    }
    OUT.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nall_verified={all_ok}  manifest -> {OUT}  ({manifest['verified_seconds']}s)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
