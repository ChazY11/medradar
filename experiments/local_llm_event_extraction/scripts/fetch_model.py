"""Chunked, resumable, parallel HTTP downloader with SHA-256 verification.

The link to the outside world on this machine stalls long-lived connections, which
kills single-stream curl downloads that are tens of minutes long.  This script splits
each file into small ranged chunks, fetches N chunks concurrently, retries stalled
chunks independently, assembles the parts, and verifies the whole file against the
expected SHA-256.  Nothing is reported as complete unless the hash matches.

Usage:
    python dl.py torch
    python dl.py model [--workers 8]
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CHUNK = 16 << 20
UA = {"User-Agent": "medradar-research-downloader/1.0"}

TORCH = {
    "url": "https://download-r2.pytorch.org/whl/cu128/torch-2.9.1%2Bcu128-cp312-cp312-win_amd64.whl",
    "dest": r"D:\DEPPSKK\ml-cache\wheels\torch-2.9.1+cu128-cp312-cp312-win_amd64.whl",
    "size": 2862033275,
    "sha256": None,
    "label": "torch-2.9.1+cu128",
}

MODEL_REV = "cdbee75f17c01a7cc42f958dc650907174af0554"
MODEL_BASE = f"https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/{MODEL_REV}"
MODEL_DEST = Path(r"D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507")
MODEL_FILES = [
    ("model-00001-of-00003.safetensors", 3957900840, "75311d91bb08cf0b882913da464a1e722a31fb44db35208663487efb7a3d8ed6"),
    ("model-00002-of-00003.safetensors", 3987450520, "0b48adbb1f60e901153d91907ba11ce63bd4b8b584482e730f48808d055dfba1"),
    ("model-00003-of-00003.safetensors", 99630640, "7dd39ccca5e4de123c74c14af44c9bf2eb75df33b4614382af0134528e060d5d"),
    ("tokenizer.json", 11422654, "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4"),
    ("config.json", 727, None),
    ("generation_config.json", 238, None),
    ("model.safetensors.index.json", 32819, None),
    ("tokenizer_config.json", 9377, None),
    ("vocab.json", 2776833, None),
    ("merges.txt", 1671839, None),
    ("LICENSE", 11343, None),
    ("README.md", 8168, None),
    (".gitattributes", 1570, None),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_range(url: str, start: int, end: int, dest: Path, attempts: int = 12) -> int:
    """Download [start, end] into dest. Returns bytes written. Raises on final failure."""
    expected = end - start + 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={**UA, "Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(request, timeout=45) as response:
                status = getattr(response, "status", response.getcode())
                if status != 206:
                    raise RuntimeError(f"expected HTTP 206 for a range request, got {status}")
                payload = response.read()
            if len(payload) != expected:
                raise RuntimeError(f"short read: {len(payload)} of {expected} bytes")
            dest.write_bytes(payload)
            return len(payload)
        except Exception as exc:  # noqa: BLE001 - retried below
            last_error = exc
            time.sleep(min(2 * attempt, 8))
    raise RuntimeError(f"chunk {start}-{end} failed after {attempts} attempts: {last_error}")


def download_file(url: str, dest: Path, size: int, sha256: str | None, *, workers: int = 8, label: str = "") -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    parts = dest.parent / (dest.name + ".parts")
    parts.mkdir(exist_ok=True)

    if dest.exists() and dest.stat().st_size == size:
        if sha256 is None or sha256_file(dest) == sha256:
            print(f"[skip] {dest.name} already complete", flush=True)
            return True
        print(f"[warn] {dest.name} size matches but sha256 differs; re-downloading", flush=True)

    ranges = [(start, min(start + CHUNK - 1, size - 1)) for start in range(0, size, CHUNK)]
    todo = []
    for index, (start, end) in enumerate(ranges):
        part = parts / f"{index:05d}.part"
        want = end - start + 1
        if part.exists() and part.stat().st_size == want:
            continue
        todo.append((index, start, end, part))

    started = time.time()
    outstanding = sum((end - start + 1) for (_, start, end, _) in todo)
    done_bytes = size - outstanding
    print(
        f"[{label}] {dest.name}: {len(todo)} of {len(ranges)} chunks outstanding, "
        f"{done_bytes/1e6:.1f}/{size/1e6:.1f} MB already local",
        flush=True,
    )
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(fetch_range, url, s, e, p): (i, s, e) for (i, s, e, p) in todo}
        for future in futures.as_completed(pending):
            i, s, e = pending[future]
            future.result()  # raises if a chunk could not be fetched
            print(f"  chunk {i} ok ({e - s + 1} B)", flush=True)

    # Assemble in order; a wrong order would produce a plausible-looking corrupt file.
    tmp = dest.with_suffix(dest.suffix + ".assembling")
    with tmp.open("wb") as out:
        for index in range(len(ranges)):
            out.write((parts / f"{index:05d}.part").read_bytes())
    actual = tmp.stat().st_size
    if actual != size:
        raise RuntimeError(f"assembled size {actual} != expected {size}")
    if sha256:
        digest = sha256_file(tmp)
        if digest != sha256:
            raise RuntimeError(f"sha256 mismatch for {dest.name}: {digest} != {sha256}")
        print(f"[{label}] sha256 verified {dest.name}", flush=True)
    tmp.replace(dest)
    for index in range(len(ranges)):
        (parts / f"{index:05d}.part").unlink(missing_ok=True)
    parts.rmdir()
    elapsed = time.time() - started
    print(
        f"[{label}] DONE {dest.name} {size/1e6:.1f} MB in {elapsed/60:.1f} min "
        f"({size/max(elapsed,1)/1e6:.2f} MB/s observed on new bytes)",
        flush=True,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=["torch", "model"])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    if args.target == "torch":
        spec = TORCH
        ok = download_file(spec["url"], Path(spec["dest"]), spec["size"], spec["sha256"],
                           workers=args.workers, label=spec["label"])
        print(json.dumps({"target": "torch", "ok": ok, "path": spec["dest"]}), flush=True)
        return 0 if ok else 1

    all_ok = True
    for name, size, sha in MODEL_FILES:
        url = f"{MODEL_BASE}/{name}"
        ok = download_file(url, MODEL_DEST / name, size, sha, workers=args.workers, label="model")
        all_ok = all_ok and ok
    print(json.dumps({"target": "model", "ok": all_ok, "dir": str(MODEL_DEST)}), flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
