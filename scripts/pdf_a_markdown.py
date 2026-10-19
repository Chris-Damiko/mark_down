# Convierte cada PDF de una carpeta a Markdown (pymupdf4llm + OCR Tesseract para páginas escaneadas).
# Uso: python scripts/pdf_a_markdown.py estatutos_instituto estatutos_instituto_md
# Requisitos: pip install "pymupdf4llm==0.0.24" pytesseract ; apt install tesseract-ocr tesseract-ocr-spa
import io
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf
import pymupdf4llm
import pytesseract
from PIL import Image

src_dir = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)


def words(s):
    return Counter(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñü]{3,}", s.lower()))


def coverage(raw, md):
    a = words(raw)
    total = sum(a.values())
    return 1.0 if not total else 1 - sum((a - words(md)).values()) / total


def ocr_page(page):
    pix = page.get_pixmap(dpi=300)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang="spa").strip()


for pdf in sorted(src_dir.glob("*.pdf")):
    doc = pymupdf.open(pdf)
    base = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False, margins=0)
    parts, ocr_pages, fallback_pages = [], 0, 0
    for i, chunk in enumerate(base):
        page = doc[i]
        raw = page.get_text()
        text = chunk["text"].strip()
        if len(raw.strip()) < 30 and page.get_images():
            text = ocr_page(page)
            ocr_pages += 1
        elif coverage(raw, text) < 0.98:
            # Imágenes de fondo o gráficos superpuestos ocultan texto: reintentar sin ellos
            best = coverage(raw, text)
            for opts in (dict(ignore_images=True),
                         dict(ignore_images=True, ignore_graphics=True, table_strategy=None)):
                alt = pymupdf4llm.to_markdown(doc, pages=[i], show_progress=False,
                                              margins=0, **opts).strip()
                if coverage(raw, alt) > best:
                    text, best = alt, coverage(raw, alt)
                if best >= 0.98:
                    break
            if text is not chunk["text"].strip():
                fallback_pages += 1
        parts.append(f"<!-- Página {i + 1} -->\n\n{text}")
    md = f"# {pdf.stem}\n\n> Fuente: `estatutos_instituto/{pdf.name}`\n\n" + "\n\n".join(parts) + "\n"
    md = md.replace("�", "ti")  # ligadura "ti" mal codificada en algunas fuentes
    (out_dir / f"{pdf.stem}.md").write_text(md, encoding="utf-8")
    print(f"{len(doc):4d} págs | OCR {ocr_pages:3d} | alt {fallback_pages:3d} | {pdf.name}", flush=True)
