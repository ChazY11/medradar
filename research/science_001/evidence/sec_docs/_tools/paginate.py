#!/usr/bin/env python
"""Report the PDF page number and printed page label enclosing given line numbers.

Usage: python paginate.py <textfile> <line> [<line> ...]
Prints for each line: the PDF page (from '==== PAGE n ===='), the printed page
label (first non-empty lines after the marker, e.g. '3-34'), and the line text.
"""
import re, sys

def main():
    path = sys.argv[1]
    wanted = [int(x) for x in sys.argv[2:]]
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    marks = []  # (index0, pageno)
    for i, ln in enumerate(lines):
        m = re.match(r"^==== PAGE (\d+) ====$", ln.strip())
        if m:
            marks.append((i, int(m.group(1))))
    def page_of(idx0):
        cur = None
        for i, n in marks:
            if i <= idx0:
                cur = (i, n)
            else:
                break
        return cur
    for w in wanted:
        idx0 = w - 1
        cur = page_of(idx0)
        hdr = []
        if cur:
            for j in range(cur[0] + 1, min(cur[0] + 6, len(lines))):
                t = lines[j].strip()
                if t:
                    hdr.append(t)
        print("line %d -> PDF page %s | header: %s" % (
            w, cur[1] if cur else "?", " / ".join(hdr[:3])))
        print("    text: %s" % lines[idx0].strip()[:400])

if __name__ == "__main__":
    main()
