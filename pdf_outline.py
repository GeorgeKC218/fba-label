"""
PDF 转曲: 把文字转为矢量路径, 避免缺字体打不开.

原理: 每页导出为 SVG (text_as_path=True), 再转回 PDF.

用法:
    python pdf_outline.py input.pdf
    python pdf_outline.py input.pdf -o output_outlined.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz

from make_labels import check_pdf_file


def outline_pdf(
    src: Path,
    dst: Path,
    *,
    dpi: float = 72.0,
) -> Path:
    """将 src PDF 转曲后写入 dst, 返回 dst."""
    check_pdf_file(src)
    src_doc = fitz.open(str(src))
    out_doc = fitz.open()

    try:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        for i in range(len(src_doc)):
            page = src_doc[i]
            svg = page.get_svg_image(matrix=mat, text_as_path=True)
            svg_doc = fitz.open("svg", svg.encode("utf-8"))
            try:
                pdf_bytes = svg_doc.convert_to_pdf()
            finally:
                svg_doc.close()

            part = fitz.open("pdf", pdf_bytes)
            try:
                out_doc.insert_pdf(part)
            finally:
                part.close()

        dst.parent.mkdir(parents=True, exist_ok=True)
        out_doc.save(str(dst), deflate=True, garbage=3)
    finally:
        src_doc.close()
        out_doc.close()

    return dst


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF 文字转曲")
    parser.add_argument("input", type=Path, help="源 PDF")
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()
    out = args.output or args.input.with_name(f"{args.input.stem}_outlined.pdf")
    outline_pdf(args.input, out)
    print(f"已转曲: {out}")


if __name__ == "__main__":
    main()
