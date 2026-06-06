"""Hand-roll a minimal multi-page PDF for testing docling path.

Pure stdlib, no external deps. Produces a valid PDF 1.4 with multiple pages,
text in Helvetica, page breaks between chapters.
"""
import sys
import zlib
from pathlib import Path

# Force UTF-8 stdout on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def build_pdf(title: str, pages: list[list[str]]) -> bytes:
    """Build a PDF with given title and list of pages (each page is a list of lines)."""
    objects: list[bytes] = []

    # Object 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # Object 2: Pages placeholder (we'll fill kids later)
    objects.append(b"2 0 obj\n<< /Type /Pages /Count %d /Kids [%s] >>\nendobj\n")

    # Object 4: Font
    objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n")

    # Object 5: Title
    title_bytes = title.encode("latin-1", errors="replace")
    objects.append(b"5 0 obj\n(" + title_bytes + b") Tj\nendobj\n")

    # Build content streams + page objects
    page_obj_indices = []
    content_obj_indices = []

    next_obj_num = 6
    page_content_pairs: list[tuple[bytes, bytes]] = []  # (page_obj, content_obj)

    for page_idx, lines in enumerate(pages, start=1):
        # Build content stream
        content_parts = ["BT", "/F1 12 Tf", "50 750 Td"]
        for i, line in enumerate(lines):
            safe = line.encode("latin-1", errors="replace")
            if i == 0:
                content_parts.append(f"({safe.decode('latin-1')}) Tj")
            else:
                content_parts.append(f"0 -15 Td ({safe.decode('latin-1')}) Tj")
        content_parts.append("ET")
        content_str = "\n".join(content_parts)
        content_bytes = content_str.encode("latin-1")
        content_stream = (
            f"{next_obj_num} 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n".encode("latin-1")
            + content_bytes
            + b"\nendstream\nendobj\n"
        )
        content_obj_indices.append(next_obj_num)
        next_obj_num += 1

        # Page object
        page_obj = (
            f"{next_obj_num} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R "
            f"/Resources << /Font << /F1 4 0 R >> >> "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {content_obj_indices[-1]} 0 R >>\n"
            f"endobj\n"
        ).encode("latin-1")
        page_obj_indices.append(next_obj_num)
        next_obj_num += 1

        page_content_pairs.append((page_obj, content_stream))

    # Now assemble
    body = b"%PDF-1.4\n"
    offsets = []

    # Object 1
    offsets.append(len(body))
    body += objects[0]

    # Object 2 (with kids)
    offsets.append(len(body))
    kids = " ".join(f"{idx} 0 R" for idx in page_obj_indices)
    body += f"2 0 obj\n<< /Type /Pages /Count {len(page_obj_indices)} /Kids [{kids}] >>\nendobj\n".encode("latin-1")

    # Object 3 (skipped? actually we used 4 for font, 5 for title)
    # We have: 1=Catalog, 2=Pages, 4=Font, 5=Title, then content+page pairs
    # Add padding to make 4 the next available? Actually, just skip object 3 and use 4
    offsets.append(0)  # placeholder for object 3 (skipped)
    offsets.append(len(body))
    body += objects[2]  # Font (object 4)
    offsets.append(len(body))
    body += objects[3]  # Title (object 5)

    for page_obj, content_stream in page_content_pairs:
        offsets.append(len(body))
        body += content_stream
        offsets.append(len(body))
        body += page_obj

    # xref table
    xref_offset = len(body)
    xref = f"xref\n0 {next_obj_num}\n0000000000 65535 f \n".encode("latin-1")
    for i in range(1, next_obj_num):
        if i in (3,):
            continue  # skipped
        offset = offsets[i - 1] if i - 1 < len(offsets) else 0
        xref += f"{offset:010d} 00000 n \n".encode("latin-1")

    body += xref
    body += f"trailer\n<< /Size {next_obj_num} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")

    return body


if __name__ == "__main__":
    out_path = Path("uploads/test_signals_systems.pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pages = [
        [
            "Chapter 1: Signal Basics",
            "",
            "1.1 Continuous-time signals are defined on a",
            "continuous time axis, e.g. x(t), t in R.",
            "Examples: sin(wt), exp(at).",
            "",
            "1.2 Discrete-time signals are defined at",
            "discrete time points, e.g. x[n], n in Z.",
            "Examples: delta[n], u[n].",
        ],
        [
            "Chapter 2: Convolution",
            "",
            "Convolution is the product-integral of two",
            "signals: (f * g)(t) = integral f(tau) g(t - tau) dtau.",
            "",
            "It is the core tool of time-domain analysis,",
            "equivalent to multiplication in the frequency",
            "domain.",
        ],
        [
            "Chapter 3: Fourier Transform",
            "",
            "F(w) = integral f(t) exp(-jwt) dt",
            "Inverse: f(t) = (1/2*pi) integral F(w) exp(jwt) dw",
            "",
            "Properties: linearity, time shift,",
            "convolution theorem.",
        ],
    ]

    pdf_bytes = build_pdf("Signals and Systems Test", pages)
    out_path.write_bytes(pdf_bytes)
    print(f"Wrote {out_path} ({len(pdf_bytes)} bytes, {len(pages)} pages)")
