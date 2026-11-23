"""OCR the scanned 510(k) Summaries that the stdlib PDF reader cannot see.

Why this is a tool and not part of the package
----------------------------------------------
``medradar`` core declares ``dependencies = []`` and that is a deliberate property: the package
installs into a bare Python with nothing to audit and nothing to licence-check. OCR needs two
things that are not stdlib - a rasteriser and an engine - so it lives here and the package never
imports it.

Licence note: rendering uses **pypdfium2** (Apache-2.0 / BSD-3-Clause). PyMuPDF is also installed
on this machine and was deliberately *not* used: it is AGPL, and pulling AGPL into the pipeline of
an MIT project is a licence decision nobody asked for. pypdfium2 does the same job cleanly.

The honesty rule this tool obeys
--------------------------------
OCR text is not a text layer, and the difference is visible to a reader years later:

* the sidecar keeps ``status="text"`` so the document is usable, and gains ``text_source="ocr"``
  plus ``ocr_pages``, ``ocr_engine`` and ``ocr_confidence_low`` so nobody mistakes it for
  publisher-supplied text;
* the original ``no_text_layer`` reason is preserved under ``pdf_reason`` rather than overwritten;
* a page that OCR reads as empty is counted, not silently skipped.

Measured context (2026-11-21): at 1,750 crawled filings the split was 682 with text / 1,013
without, concentrated in 2010-2012. Those scans are the only remaining way to grow the corpus.

    python tools/ocr_scan.py --probe K101825        # what does OCR actually see?
    python tools/ocr_scan.py --limit 50             # convert 50 scanned documents
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

#: 510(k) summaries are short; the sections we want are in the first few pages. Bounding the
#: page count is what keeps OCR at ~2 s/document instead of ~30 s.
MAX_PAGES = 8
#: ~200 DPI. Higher doubles the cost and improves tesseract very little on a clean scan.
RENDER_SCALE = 200 / 72


def find_tesseract() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in TESSERACT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def ocr_pdf(data: bytes, *, engine: str, max_pages: int = MAX_PAGES,
            timeout: float = 60.0) -> dict:
    """Render each page and OCR it. Returns text plus what it actually managed to read."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(data)
    pages_read = 0
    empty_pages = 0
    chunks: list[str] = []
    try:
        total = len(document)
        for index in range(min(total, max_pages)):
            page = document[index]
            try:
                image = page.render(scale=RENDER_SCALE).to_pil()
            except Exception:  # noqa: BLE001 - a broken page must not lose the document
                empty_pages += 1
                continue
            with tempfile.TemporaryDirectory() as folder:
                png = Path(folder) / "page.png"
                image.save(png, format="PNG")
                try:
                    result = subprocess.run(
                        [engine, str(png), "stdout", "-l", "eng", "--psm", "6"],
                        capture_output=True, timeout=timeout,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except subprocess.TimeoutExpired:
                    empty_pages += 1
                    continue
            text = result.stdout.decode("utf-8", "replace").strip()
            if len(text) < 20:
                empty_pages += 1
                continue
            pages_read += 1
            chunks.append(text)
    finally:
        document.close()

    return {
        "text": "\n\n".join(chunks),
        "pages_total": total,
        "pages_read": pages_read,
        "pages_empty": empty_pages,
        "engine_version": engine,
    }


def engine_version(engine: str) -> str:
    try:
        result = subprocess.run([engine, "--version"], capture_output=True, timeout=20,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.stdout.decode("utf-8", "replace").splitlines()[0].strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def probe(k_number: str, target: Path, engine: str) -> int:
    """Fetch one document, OCR it, and show what came out. Diagnostics before batch work."""
    from medradar.radar.documents import derive_510k_pdf_url, split_sections
    from medradar.radar.http import HostPolicy, PoliteFetcher

    fetcher = PoliteFetcher(
        user_agent="MedRadar/0.1 (+https://github.com/ChazY11/medradar; research)",
        policies={"www.accessdata.fda.gov": HostPolicy(requests_per_second=2.0,
                                                       timeout_seconds=120.0)},
        max_requests=10,
    )
    url = derive_510k_pdf_url(k_number)
    print(f"fetching {url}")
    result = fetcher.get_bytes(url, allow_not_found=True)
    if result.status != 200 or not result.payload:
        print(f"no document (status {result.status})", file=sys.stderr)
        return 1
    print(f"{len(result.payload):,} bytes")

    started = time.perf_counter()
    outcome = ocr_pdf(result.payload, engine=engine)
    elapsed = time.perf_counter() - started
    text = outcome["text"]
    print(f"pages {outcome['pages_read']}/{outcome['pages_total']} read, "
          f"{outcome['pages_empty']} empty, {elapsed:.1f}s, {len(text):,} chars")
    sections = split_sections(text)
    print("sections:", json.dumps({k: len(v) for k, v in sections.items()},
                                  ensure_ascii=False))
    print("--- first 700 chars ---")
    print(text[:700])
    return 0 if text else 1


def convert(target: Path, *, limit: int | None, engine: str, rate: float) -> int:
    """OCR every sidecar still marked ``no_text_layer`` and upgrade it in place."""
    import pypdfium2  # noqa: F401 - fail early if the rasteriser is missing

    from medradar.radar.documents import derive_510k_pdf_url, split_sections
    from medradar.radar.http import HostPolicy, PoliteFetcher

    fetcher = PoliteFetcher(
        user_agent="MedRadar/0.1 (+https://github.com/ChazY11/medradar; research)",
        policies={"www.accessdata.fda.gov": HostPolicy(requests_per_second=rate,
                                                       timeout_seconds=120.0)},
        max_requests=5_000_000,
    )
    pending = []
    for path in sorted(target.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("status") == "no_text_layer":
            pending.append((path, payload))
    print(f"scanned documents pending OCR: {len(pending):,}")
    if limit is not None:
        pending = pending[:limit]

    version = engine_version(engine)
    stats = {"ocr_ok": 0, "ocr_empty": 0, "fetch_failed": 0, "errored": 0, "chars": 0}
    started = time.perf_counter()
    for index, (path, payload) in enumerate(pending, start=1):
        k_number = str(payload.get("identifier") or "").strip().upper()
        try:
            result = fetcher.get_bytes(derive_510k_pdf_url(k_number), allow_not_found=True)
            if result.status != 200 or not result.payload:
                stats["fetch_failed"] += 1
                continue
            outcome = ocr_pdf(result.payload, engine=engine)
            text = outcome["text"]
            if not text:
                stats["ocr_empty"] += 1
                payload["ocr_attempted_at_epoch"] = int(time.time())
                payload["ocr_result"] = "empty"
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                encoding="utf-8")
                continue
            sections = split_sections(text)
            payload.update({
                "status": "text",
                "text_source": "ocr",
                "pdf_reason": payload.get("pdf_reason") or payload.get("note"),
                "char_count": len(text),
                "text_chars": len(text),
                "sections": sections,
                "ocr_pages": outcome["pages_read"],
                "ocr_pages_empty": outcome["pages_empty"],
                "ocr_engine": version,
                "ocr_confidence_low": True,
                "note": "text recovered by OCR from an image-only PDF; not a publisher text layer",
            })
            payload.pop("http_status", None)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            path.with_suffix(".txt").write_text(text, encoding="utf-8")
            stats["ocr_ok"] += 1
            stats["chars"] += len(text)
        except Exception as error:  # noqa: BLE001 - one bad document must not end the batch
            stats["errored"] += 1
            payload["ocr_error"] = f"{type(error).__name__}: {error}"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if index % 25 == 0:
            elapsed = time.perf_counter() - started
            print(f"  {index:,}/{len(pending):,} | ok={stats['ocr_ok']} "
                  f"empty={stats['ocr_empty']} fetchfail={stats['fetch_failed']} "
                  f"err={stats['errored']} | {index/elapsed:.2f}/s", flush=True)
    print("done:", json.dumps(stats, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=r"D:\DEPPSKK\_intel\corpus510k")
    parser.add_argument("--probe", help="a K number to try first")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--rate", type=float, default=2.0,
                        help="requests/second against accessdata.fda.gov")
    args = parser.parse_args()

    engine = find_tesseract()
    if engine is None:
        print("tesseract not found. Install with: winget install UB-Mannheim.TesseractOCR",
              file=sys.stderr)
        return 2
    print(f"engine: {engine}")
    print(f"version: {engine_version(engine)}")

    if args.probe:
        return probe(args.probe.upper(), Path(args.target), engine)
    return convert(Path(args.target), limit=args.limit, engine=engine, rate=args.rate)


if __name__ == "__main__":
    raise SystemExit(main())
