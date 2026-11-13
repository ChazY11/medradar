#!/usr/bin/env python
"""Extract readable text from cached raw pages into raw/<id>.txt.

HTML: lxml -> non-duplicating block-level text; table rows joined with ' || ';
      <pre> kept verbatim inside ~~~ fences; script/style dropped.
PDF: PyMuPDF with ===== PAGE n ===== markers so quotes can cite page numbers.
Cached originals are never modified.  Existing .txt is overwritten.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(os.path.dirname(HERE), "raw")
META = os.path.join(RAW, "_meta.json")

BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "pre",
         "caption", "blockquote", "summary", "figcaption"}
FENCE = "~~~"


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def html_to_text(path):
    from lxml import html as LH
    with open(path, "rb") as f:
        data = f.read()
    doc = LH.fromstring(data)
    for bad in doc.xpath("//script|//style|//noscript|//svg|//nav|//footer|//header"):
        bad.getparent().remove(bad)

    out = []
    for el in doc.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag == "pre":
            txt = el.text_content()
            if txt.strip():
                out.append(FENCE)
                out.extend(txt.rstrip().splitlines())
                out.append(FENCE)
            continue
        if tag == "tr":
            if el.xpath(".//p|.//div|.//li|.//pre|.//table"):
                continue
            cells = []
            for c in el.iter():
                if isinstance(c.tag, str) and c.tag in ("td", "th"):
                    cells.append(_norm(c.text_content()))
            if cells:
                out.append(" || ".join(cells))
            continue
        if tag in ("td", "th"):
            if any(isinstance(a.tag, str) and a.tag == "tr" for a in el.iterancestors()):
                continue
        if tag in BLOCK:
            if el.xpath(".//p|.//li|.//div|.//table|.//h1|.//h2|.//h3|.//pre|.//ul|.//ol"):
                continue
            txt = _norm(el.text_content())
            if txt:
                if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    out.append("#" * int(tag[1]) + " " + txt)
                else:
                    out.append(txt)
    final = []
    for ln in out:
        if ln and final and ln == final[-1]:
            continue
        final.append(ln)
    return "\n".join(final)


def pdf_to_text(path):
    import fitz
    doc = fitz.open(path)
    parts = []
    for i, page in enumerate(doc, start=1):
        parts.append("\n==== PAGE %d ====\n" % i)
        parts.append(page.get_text("text"))
    parts.append("\n==== END (%d pages) ====\n" % len(doc))
    return "".join(parts)


def main():
    meta = json.load(open(META, "r", encoding="utf-8"))
    for rec in meta["records"]:
        fn = rec.get("file")
        if not fn:
            continue
        src = os.path.join(RAW, fn)
        if not os.path.exists(src):
            continue
        stem, ext = os.path.splitext(fn)[0], os.path.splitext(fn)[1].lower()
        out = os.path.join(RAW, stem + ".txt")
        try:
            if ext == ".html":
                txt = html_to_text(src)
            elif ext == ".pdf":
                txt = pdf_to_text(src)
            elif ext in (".xml", ".json", ".txt", ".bin"):
                txt = open(src, "r", encoding="utf-8", errors="replace").read()
            else:
                continue
            with open(out, "w", encoding="utf-8") as f:
                f.write(txt)
            rec["text_file"] = stem + ".txt"
            print("text %s.txt (%d chars)" % (stem, len(txt)))
        except Exception as e:
            print("TEXTFAIL %s: %s: %s" % (fn, type(e).__name__, e))
    json.dump(meta, open(META, "w", encoding="utf-8"), indent=2)


if __name__ == "__main__":
    main()