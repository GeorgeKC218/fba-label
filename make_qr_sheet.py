"""
将「100 二维码 + 底部 4 条码」排成 A4。

源 PDF 结构: 每 101 页一组 = 100 个二维码 + 1 页外箱条码。
产品编号位数按总数自适应: 4000 → 0001..4000；25200 → 00001..25200。
箱号: 第 n 页四个条码均为 {n}-{总箱数}，如 001-252 / 01-40。
"""

from __future__ import annotations

import argparse
import io
import time
from pathlib import Path

import fitz

PAGE_W, PAGE_H = 595.44, 841.68
COLS, ROWS = 10, 10
QR_W, QR_H = 44.0, 44.0
GAP_X, GAP_Y = 10.0, 13.0
PITCH_X, PITCH_Y = QR_W + GAP_X, QR_H + GAP_Y
QR_X0 = (PAGE_W - (COLS * QR_W + (COLS - 1) * GAP_X)) / 2
QR_Y0 = 50.0
LABEL_SIZE = 6.1

BC_RECTS = [
    fitz.Rect(66.96, 653.28, 147.12, 699.24),
    fitz.Rect(163.68, 653.28, 243.84, 699.24),
    fitz.Rect(260.40, 653.28, 340.56, 699.24),
    fitz.Rect(357.12, 653.28, 437.28, 699.24),
]

QR_CLIP = fitz.Rect(25.44, 5.71, 83.64, 63.90)
BC_BARS = fitz.Rect(6.0, 6.0, 104.28, 46.32)

GROUP_SIZE = 101  # 100 QR + 1 barcode
QR_PER_GROUP = 100

_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\simsun.ttc"),
    Path(r"C:\Windows\Fonts\simsun.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def resolve_cjk_font() -> tuple[str, Path | None, fitz.Font]:
    """返回 (fontname, fontfile|None, Font)。云端无宋体时用 PyMuPDF 内置 china-s。"""
    for p in _FONT_CANDIDATES:
        if p.exists():
            return p.stem[:6] or "f0", p, fitz.Font(fontfile=str(p))
    # Streamlit Cloud / Linux 回退 (PyMuPDF 内置 CJK)
    return "china-s", None, fitz.Font("cjk")


def digit_width(n: int) -> int:
    """按最大值决定补零位数: 4000→4, 252→3, 40→2。"""
    return max(len(str(max(n, 1))), 1)


def _classify_page(page) -> str:
    imgs = page.get_image_info()
    if not imgs:
        return "?"
    b = imgs[0]["bbox"]
    w, h = b[2] - b[0], b[3] - b[1]
    return "BC" if w > h * 1.2 else "QR"


def detect_groups(doc: fitz.Document) -> int:
    n = len(doc)
    if n % GROUP_SIZE != 0:
        raise ValueError(
            f"源页数 {n} 不能被 {GROUP_SIZE} 整除，无法按 100码+1条码 分组"
        )
    groups = n // GROUP_SIZE
    for g in (0, groups - 1):
        base = g * GROUP_SIZE
        for i in range(QR_PER_GROUP):
            if _classify_page(doc[base + i]) != "QR":
                raise ValueError(f"组 {g + 1} 第 {i + 1} 页不是二维码")
        if _classify_page(doc[base + QR_PER_GROUP]) != "BC":
            raise ValueError(f"组 {g + 1} 第 101 页不是条码")
    return groups


def peek_sheet_info(src: Path) -> dict:
    """快速查看源文件分组信息（网页预览用）。"""
    doc = fitz.open(src)
    try:
        groups = detect_groups(doc)
        products = groups * QR_PER_GROUP
        return {
            "pages": len(doc),
            "groups": groups,
            "products": products,
            "product_digits": digit_width(products),
            "box_digits": digit_width(groups),
        }
    finally:
        doc.close()


def insert_label(
    page: fitz.Page,
    text: str,
    x_center: float,
    y: float,
    font: fitz.Font,
    fontname: str,
    fontsize: float = LABEL_SIZE,
) -> None:
    tw = font.text_length(text, fontsize=fontsize)
    page.insert_text(
        (x_center - tw / 2, y),
        text,
        fontname=fontname,
        fontsize=fontsize,
        color=(0, 0, 0),
    )


def make_sheet(
    src: Path,
    out: Path | None = None,
    *,
    prefix: str = "406-078",
    start_group: int = 0,
    max_groups: int | None = None,
    label_digits: int | None = None,
    box_digits: int | None = None,
) -> Path | bytes:
    """生成排版 PDF。

    label_digits / box_digits 为 None 时按总数自动决定位数。
    out 为 None 时返回 PDF bytes；否则写入文件并返回路径。
    """
    prefix = (prefix or "").strip().rstrip("-")
    if not prefix:
        raise ValueError("编号前缀不能为空")

    fontname, fontfile, font = resolve_cjk_font()

    src_doc = fitz.open(src)
    try:
        groups = detect_groups(src_doc)
        if start_group < 0 or start_group >= groups:
            raise ValueError(f"start_group 无效: {start_group}, 共 {groups} 组")
        end_group = (
            groups if max_groups is None else min(groups, start_group + max_groups)
        )
        total_products = groups * QR_PER_GROUP
        prod_digits = (
            label_digits if label_digits and label_digits > 0 else digit_width(total_products)
        )
        box_w = box_digits if box_digits and box_digits > 0 else digit_width(groups)

        out_doc = fitz.open()
        t0 = time.time()
        total = end_group - start_group
        print(
            f"源: {Path(src).name}  共 {groups} 组 / {total_products} 个二维码  "
            f"前缀={prefix}  产品位数={prod_digits}  箱号位数={box_w}"
        )
        print(f"生成组 {start_group + 1} .. {end_group}  (共 {total} 页 A4)")

        for gi, g in enumerate(range(start_group, end_group)):
            base = g * GROUP_SIZE
            page = out_doc.new_page(width=PAGE_W, height=PAGE_H)
            if fontfile is not None:
                page.insert_font(fontname=fontname, fontfile=str(fontfile))

            for i in range(QR_PER_GROUP):
                row, col = divmod(i, COLS)
                x = QR_X0 + col * PITCH_X
                y = QR_Y0 + row * PITCH_Y
                page.show_pdf_page(
                    fitz.Rect(x, y, x + QR_W, y + QR_H),
                    src_doc,
                    base + i,
                    clip=QR_CLIP,
                )
                seq = g * QR_PER_GROUP + i + 1
                label = f"{prefix}-{seq:0{prod_digits}d}"
                insert_label(
                    page, label, x + QR_W / 2, y + QR_H + 7.0, font, fontname
                )

            bc_page = base + QR_PER_GROUP
            raw = (src_doc[bc_page].get_text("text") or "").replace("\xa0", " ").strip()
            gs1 = raw.splitlines()[0].strip() if raw else ""
            if gs1.startswith("(00)") and len(gs1) > 4 and gs1[4] != " ":
                gs1 = "(00) " + gs1[4:]

            box_label = f"{g + 1:0{box_w}d}-{groups:0{box_w}d}"
            for dest in BC_RECTS:
                page.show_pdf_page(dest, src_doc, bc_page, clip=BC_BARS)
                cx = (dest.x0 + dest.x1) / 2
                if gs1:
                    insert_label(page, gs1, cx, dest.y1 + 8.0, font, fontname)
                insert_label(page, box_label, cx, dest.y1 + 16.5, font, fontname)

            if (gi + 1) % 10 == 0 or gi == 0 or gi + 1 == total:
                elapsed = time.time() - t0
                rate = (gi + 1) / elapsed if elapsed > 0 else 0
                eta = (total - gi - 1) / rate if rate > 0 else 0
                print(
                    f"  [{gi + 1}/{total}] 组{g + 1} "
                    f"产品 {g * QR_PER_GROUP + 1}-{(g + 1) * QR_PER_GROUP}  "
                    f"{elapsed:.0f}s elapsed, ETA {eta:.0f}s"
                )

        if out is None:
            buf = io.BytesIO()
            out_doc.save(buf, deflate=True, garbage=3)
            out_doc.close()
            print(f"完成(内存) {time.time() - t0:.0f}s")
            return buf.getvalue()

        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                tmp = out.with_name(out.stem + f"_{int(time.time())}.pdf.tmp")
        print(f"写入 {tmp} …")
        out_doc.save(tmp, deflate=True, garbage=3)
        out_doc.close()
        final = out
        try:
            if final.exists():
                final.unlink()
            tmp.rename(final)
        except OSError:
            final = out.with_name(f"{out.stem}_{int(time.time())}{out.suffix}")
            tmp.rename(final)
            print(f"原路径被占用，已另存为: {final.name}")
        print(
            f"完成: {final}  ({final.stat().st_size / 1024 / 1024:.1f} MB, "
            f"{time.time() - t0:.0f}s)"
        )
        return final
    finally:
        src_doc.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="100二维码+4条码 A4 批量排版")
    ap.add_argument("input", type=Path, help="源 PDF (100码+1条码循环)")
    ap.add_argument("-o", "--output", type=Path, default=None, help="输出 PDF")
    ap.add_argument(
        "--prefix",
        type=str,
        default="406-078",
        help="产品编号前缀, 如 406-078 → 406-078-0001",
    )
    ap.add_argument("--start-group", type=int, default=0, help="从第几组开始 (0-based)")
    ap.add_argument("--max-groups", type=int, default=None, help="最多生成多少组/页")
    ap.add_argument(
        "--digits",
        type=int,
        default=0,
        help="产品编号位数; 0=按总数自动 (4000→4位)",
    )
    args = ap.parse_args()
    out = args.output or args.input.with_name(f"{args.input.stem}_A4_sheets.pdf")
    make_sheet(
        args.input,
        out,
        prefix=args.prefix,
        start_group=args.start_group,
        max_groups=args.max_groups,
        label_digits=args.digits or None,
    )


if __name__ == "__main__":
    main()
