"""预览源 PDF 第 N 页的有效内容 bbox (PyMuPDF).

用法:
    python preview_bbox.py 11_ai.pdf
    python preview_bbox.py 11_ai.pdf 5
"""

from __future__ import annotations

import sys
from pathlib import Path

from make_labels import compute_content_bbox_pymupdf, get_content_bbox
from pypdf import PdfReader

MM_PER_PT = 25.4 / 72.0


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = Path(sys.argv[1])
    page_idx = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    page = reader.pages[page_idx]
    box = page.mediabox

    print(f"文件: {path}, 第 {page_idx + 1} / {len(reader.pages)} 页")
    print(
        f"MediaBox: {float(box.width):.2f} x {float(box.height):.2f} pt"
        f"  ({float(box.width) * MM_PER_PT:.2f} x {float(box.height) * MM_PER_PT:.2f} mm)"
    )

    bbox_pymupdf = compute_content_bbox_pymupdf(path, page_idx)
    bbox = get_content_bbox(path, page_idx, page, reader)

    for name, b in (("PyMuPDF", bbox_pymupdf), ("使用", bbox)):
        bw = b[2] - b[0]
        bh = b[3] - b[1]
        print(f"\n[{name}] 内容 bbox: ({b[0]:.2f}, {b[1]:.2f}) - ({b[2]:.2f}, {b[3]:.2f})")
        print(f"  尺寸 (pt): {bw:.2f} x {bh:.2f}")
        print(f"  尺寸 (mm): {bw * MM_PER_PT:.2f} x {bh * MM_PER_PT:.2f} mm")
        print(f"  距上边距 (pt): {float(box.height) - b[3]:.2f}")
        print(f"  距下边距 (pt): {b[1] - float(box.bottom):.2f}")
        print(f"  距左边距 (pt): {b[0] - float(box.left):.2f}")
        print(f"  距右边距 (pt): {float(box.right) - b[2]:.2f}")

    cell_w, cell_h = 297.6377, 240.0
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    fill_scale = min(cell_w / bw, cell_h / bh)
    scale_1to1 = min(1.0, fill_scale)
    print(f"\n格子: {cell_w:.2f} x {cell_h:.2f} pt")
    print(f"  若 --fill 放大填满: scale = {fill_scale:.4f}")
    print(f"  默认 1:1 不放大:     scale = {scale_1to1:.4f}")


if __name__ == "__main__":
    main()
