"""
将「N 个二维码 + 1 个外箱条码」排成多页 A4。

源 PDF 结构（循环）: N 页二维码 + 1 页条码。
输出: 每箱 ceil(N/100) 张 A4；每张最多 10×10=100 个二维码，
      该箱所有页底部都印同一条码（4 份），避免认错箱。

产品编号位数按总数自适应；箱号为 {箱序}-{总箱数}。
"""

from __future__ import annotations

import argparse
import io
import math
import time
from pathlib import Path

import fitz

PAGE_W, PAGE_H = 595.44, 841.68
COLS, ROWS = 10, 10
QR_PER_PAGE = COLS * ROWS  # 100
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

_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\simsun.ttc"),
    Path(r"C:\Windows\Fonts\simsun.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def resolve_cjk_font() -> tuple[str, Path | None, fitz.Font]:
    for p in _FONT_CANDIDATES:
        if p.exists():
            return p.stem[:6] or "f0", p, fitz.Font(fontfile=str(p))
    return "china-s", None, fitz.Font("cjk")


def digit_width(n: int) -> int:
    return max(len(str(max(n, 1))), 1)


def _classify_page(page) -> str:
    imgs = page.get_image_info()
    if not imgs:
        return "?"
    b = imgs[0]["bbox"]
    w, h = b[2] - b[0], b[3] - b[1]
    return "BC" if w > h * 1.2 else "QR"


def detect_groups(doc: fitz.Document, qr_per_box: int) -> int:
    if qr_per_box < 1:
        raise ValueError("每箱二维码数量必须 ≥ 1")
    group_size = qr_per_box + 1
    n = len(doc)
    if n % group_size != 0:
        raise ValueError(
            f"源页数 {n} 不能被 {group_size}（{qr_per_box}码+1条码）整除，"
            f"请确认「每箱二维码数」是否填对"
        )
    groups = n // group_size
    for g in (0, groups - 1):
        base = g * group_size
        for i in range(qr_per_box):
            if _classify_page(doc[base + i]) != "QR":
                raise ValueError(f"组 {g + 1} 第 {i + 1} 页不是二维码")
        if _classify_page(doc[base + qr_per_box]) != "BC":
            raise ValueError(f"组 {g + 1} 第 {qr_per_box + 1} 页不是条码")
    return groups


def peek_sheet_info(src: Path, qr_per_box: int = 100) -> dict:
    doc = fitz.open(src)
    try:
        groups = detect_groups(doc, qr_per_box)
        products = groups * qr_per_box
        sheets_per_box = math.ceil(qr_per_box / QR_PER_PAGE)
        return {
            "pages": len(doc),
            "groups": groups,
            "products": products,
            "qr_per_box": qr_per_box,
            "sheets_per_box": sheets_per_box,
            "out_pages": groups * sheets_per_box,
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


def _draw_barcodes(
    page: fitz.Page,
    src_doc: fitz.Document,
    bc_page: int,
    gs1: str,
    box_label: str,
    font: fitz.Font,
    fontname: str,
) -> None:
    for dest in BC_RECTS:
        page.show_pdf_page(dest, src_doc, bc_page, clip=BC_BARS)
        cx = (dest.x0 + dest.x1) / 2
        if gs1:
            insert_label(page, gs1, cx, dest.y1 + 8.0, font, fontname)
        insert_label(page, box_label, cx, dest.y1 + 16.5, font, fontname)


def make_sheet(
    src: Path,
    out: Path | None = None,
    *,
    prefix: str = "406-078",
    qr_per_box: int = 100,
    start_group: int = 0,
    max_groups: int | None = None,
    label_digits: int | None = None,
    box_digits: int | None = None,
) -> Path | bytes:
    prefix = (prefix or "").strip().rstrip("-")
    if not prefix:
        raise ValueError("编号前缀不能为空")
    if qr_per_box < 1:
        raise ValueError("每箱二维码数量必须 ≥ 1")

    fontname, fontfile, font = resolve_cjk_font()
    group_size = qr_per_box + 1
    sheets_per_box = math.ceil(qr_per_box / QR_PER_PAGE)

    src_doc = fitz.open(src)
    try:
        groups = detect_groups(src_doc, qr_per_box)
        if start_group < 0 or start_group >= groups:
            raise ValueError(f"start_group 无效: {start_group}, 共 {groups} 组")
        end_group = (
            groups if max_groups is None else min(groups, start_group + max_groups)
        )
        total_products = groups * qr_per_box
        prod_digits = (
            label_digits
            if label_digits and label_digits > 0
            else digit_width(total_products)
        )
        box_w = box_digits if box_digits and box_digits > 0 else digit_width(groups)

        out_doc = fitz.open()
        t0 = time.time()
        total_boxes = end_group - start_group
        print(
            f"源: {Path(src).name}  共 {groups} 箱 / {total_products} 个二维码  "
            f"每箱={qr_per_box} → 每箱 {sheets_per_box} 张A4  "
            f"前缀={prefix}  产品位数={prod_digits}  箱号位数={box_w}"
        )

        for gi, g in enumerate(range(start_group, end_group)):
            base = g * group_size
            bc_page = base + qr_per_box
            raw = (src_doc[bc_page].get_text("text") or "").replace("\xa0", " ").strip()
            gs1 = raw.splitlines()[0].strip() if raw else ""
            if gs1.startswith("(00)") and len(gs1) > 4 and gs1[4] != " ":
                gs1 = "(00) " + gs1[4:]
            box_label = f"{g + 1:0{box_w}d}-{groups:0{box_w}d}"

            # 该箱二维码拆到多张 A4；每张都印同一条码
            for sheet_i in range(sheets_per_box):
                page = out_doc.new_page(width=PAGE_W, height=PAGE_H)
                if fontfile is not None:
                    page.insert_font(fontname=fontname, fontfile=str(fontfile))

                start_i = sheet_i * QR_PER_PAGE
                end_i = min(start_i + QR_PER_PAGE, qr_per_box)
                for local, qi in enumerate(range(start_i, end_i)):
                    row, col = divmod(local, COLS)
                    x = QR_X0 + col * PITCH_X
                    y = QR_Y0 + row * PITCH_Y
                    page.show_pdf_page(
                        fitz.Rect(x, y, x + QR_W, y + QR_H),
                        src_doc,
                        base + qi,
                        clip=QR_CLIP,
                    )
                    seq = g * qr_per_box + qi + 1
                    label = f"{prefix}-{seq:0{prod_digits}d}"
                    insert_label(
                        page, label, x + QR_W / 2, y + QR_H + 7.0, font, fontname
                    )

                _draw_barcodes(
                    page, src_doc, bc_page, gs1, box_label, font, fontname
                )

            if (gi + 1) % 10 == 0 or gi == 0 or gi + 1 == total_boxes:
                elapsed = time.time() - t0
                rate = (gi + 1) / elapsed if elapsed > 0 else 0
                eta = (total_boxes - gi - 1) / rate if rate > 0 else 0
                print(
                    f"  [{gi + 1}/{total_boxes}] 箱{g + 1} "
                    f"产品 {g * qr_per_box + 1}-{(g + 1) * qr_per_box}  "
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
    ap = argparse.ArgumentParser(description="N二维码+1条码 → 多页A4 拼版")
    ap.add_argument("input", type=Path, help="源 PDF")
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--prefix", type=str, default="406-078")
    ap.add_argument(
        "--qr-per-box",
        type=int,
        default=100,
        help="每箱对应几个二维码 (100 / 360 …)",
    )
    ap.add_argument("--start-group", type=int, default=0)
    ap.add_argument("--max-groups", type=int, default=None)
    ap.add_argument("--digits", type=int, default=0, help="产品编号位数; 0=自动")
    args = ap.parse_args()
    out = args.output or args.input.with_name(f"{args.input.stem}_A4_sheets.pdf")
    make_sheet(
        args.input,
        out,
        prefix=args.prefix,
        qr_per_box=args.qr_per_box,
        start_group=args.start_group,
        max_groups=args.max_groups,
        label_digits=args.digits or None,
    )


if __name__ == "__main__":
    main()
