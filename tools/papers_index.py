"""Build the paper-to-device index that the device view uses for its fifth section.

    python3 tools/papers_index.py --corpus /srv/medradar/intel/papers --summary
    python3 tools/papers_index.py --corpus /srv/medradar/intel/papers --rebuild

Nothing here talks to the network: it reads the corpus the full-text lane already harvested and
writes `paper_term` rows next to the device register. Run it after a harvest, and after the
register is refreshed (the vocabulary comes from the register).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.radar.papers_index import index_corpus, summary, tables_present, vocabulary
from medradar.radar.reference import UdiReference

DEFAULT_REFERENCE = "/srv/medradar/reference_slim.db"
DEFAULT_CORPUS = "/srv/medradar/intel/papers"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--rebuild", action="store_true",
                        help="clear the index before rebuilding (the vocabulary changes)")
    parser.add_argument("--limit", type=int, default=0, help="index only the first N papers")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    reference_path = Path(args.reference)
    corpus = Path(args.corpus)
    if not reference_path.exists():
        print(f"reference store not found: {reference_path}", file=sys.stderr)
        return 2
    if not corpus.exists():
        print(f"corpus directory not found: {corpus}", file=sys.stderr)
        return 2

    store = UdiReference(str(reference_path))
    try:
        if args.summary and not args.rebuild:
            print(json.dumps(summary(store), ensure_ascii=False))
            return 0
        if args.rebuild and tables_present(store):
            store.conn.execute("DELETE FROM paper_term")
            store.conn.commit()
            print("  index cleared", file=sys.stderr)
        voc = vocabulary(store)
        print(f"  vocabulary from the register: {len(voc):,} terms", file=sys.stderr)
        result = index_corpus(store, corpus, vocab=voc,
                              limit=args.limit or None)
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        print(json.dumps(summary(store), ensure_ascii=False))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
