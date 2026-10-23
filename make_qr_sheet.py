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
import shutil
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

# 工厂对刀线（四角 L，来自对角线模板；在页边空白，不改动二维码/条码坐标）
CROP_ARM = 19.84
CROP_W = 1.42
CROP_TL = (24.89, 32.80)
CROP_TR = (570.55, 32.80)
CROP_BL = (24.89, 737.36)
CROP_BR = (570.55, 737.36)

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


def detect_qr_per_box(doc: fitz.Document, max_scan: int = 10000) -> int:
    """扫第一组：连续二维码页直到出现条码页 → 每箱二维码数。

    例：第 361 页是条码 → 返回 360（360 码 + 1 条码）。
    """
    n = len(doc)
    if n < 2:
        raise ValueError("源 PDF 页数太少，无法识别「二维码+条码」结构")
    limit = min(n, max_scan)
    qr_count = 0
    for i in range(limit):
        kind = _classify_page(doc[i])
        if kind == "QR":
            qr_count += 1
            continue
        if kind == "BC":
            if qr_count < 1:
                raise ValueError("第 1 页就是条码，无法识别每箱二维码数量")
            return qr_count
        raise ValueError(f"第 {i + 1} 页无法识别为二维码或条码")
    raise ValueError(
        f"前 {limit} 页未找到条码页，请手动填写「每箱二维码数」"
        "（或确认源文件是「N 个二维码 + 1 个条码」循环）"
    )


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
    # 只抽查首尾组，避免大文件全量扫描过慢
    for g in (0, groups - 1):
        base = g * group_size
        # 抽查组内首、中、末二维码页 + 条码页
        sample_idx = {0, qr_per_box // 2, qr_per_box - 1}
        for i in sample_idx:
            if _classify_page(doc[base + i]) != "QR":
                raise ValueError(f"组 {g + 1} 第 {i + 1} 页不是二维码")
        if _classify_page(doc[base + qr_per_box]) != "BC":
            raise ValueError(f"组 {g + 1} 第 {qr_per_box + 1} 页不是条码")
    return groups


def peek_sheet_info(src: Path, qr_per_box: int | None = None) -> dict:
    """qr_per_box=None 时自动识别（扫到第一条码页）。"""
    doc = fitz.open(src)
    try:
        auto = qr_per_box is None or qr_per_box <= 0
        if auto:
            qr_per_box = detect_qr_per_box(doc)
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
            "auto_detected": auto,
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


def _draw_crop_marks(page: fitz.Page) -> None:
    """四角 L 形对刀线（页边空白，不压二维码/条码）。"""
    color = (0, 0, 0)
    a = CROP_ARM

    def L(cx: float, cy: float, right: bool, down: bool) -> None:
        hx = cx + a if right else cx - a
        vy = cy + a if down else cy - a
        page.draw_line(fitz.Point(cx, cy), fitz.Point(hx, cy), color=color, width=CROP_W)
        page.draw_line(fitz.Point(cx, cy), fitz.Point(cx, vy), color=color, width=CROP_W)

    tlx, tly = CROP_TL
    trx, try_ = CROP_TR
    blx, bly = CROP_BL
    brx, bry = CROP_BR
    # 与模板一致：角点在外侧，短线伸向版心
    L(tlx, tly, right=True, down=True)
    L(trx, try_, right=False, down=True)
    L(blx, bly, right=True, down=False)
    L(brx, bry, right=False, down=False)


def make_sheet(
    src: Path,
    out: Path | None = None,
    *,
    prefix: str = "406-078",
    qr_per_box: int | None = 100,
    start_group: int = 0,
    max_groups: int | None = None,
    label_digits: int | None = None,
    box_digits: int | None = None,
    product_start: int = 1,
    box_start: int = 1,
    box_total: int | None = None,
    grand_total: int | None = None,
    crop_marks: bool = True,
    quiet: bool = False,
) -> Path | bytes:
    """product_start/box_start 用于多文件续编；grand_total/box_total 决定补零位数与箱号分母。"""
    prefix = (prefix or "").strip().rstrip("-")
    if not prefix:
        raise ValueError("编号前缀不能为空")
    if product_start < 1:
        raise ValueError("产品起始编号必须 ≥ 1")
    if box_start < 1:
        raise ValueError("箱号起始必须 ≥ 1")

    fontname, fontfile, font = resolve_cjk_font()

    def log(msg: str) -> None:
        if not quiet:
            print(msg)

    src_doc = fitz.open(src)
    try:
        if qr_per_box is None or qr_per_box <= 0:
            qr_per_box = detect_qr_per_box(src_doc)
            log(f"自动识别：每箱 {qr_per_box} 个二维码（第 {qr_per_box + 1} 页为条码）")
        if qr_per_box < 1:
            raise ValueError("每箱二维码数量必须 ≥ 1")
        group_size = qr_per_box + 1
        sheets_per_box = math.ceil(qr_per_box / QR_PER_PAGE)
        groups = detect_groups(src_doc, qr_per_box)
        if start_group < 0 or start_group >= groups:
            raise ValueError(f"start_group 无效: {start_group}, 共 {groups} 组")
        end_group = (
            groups if max_groups is None else min(groups, start_group + max_groups)
        )
        file_products = groups * qr_per_box
        # 补零：优先手动位数 → 整单总数 → 本文件末号
        end_seq = product_start + file_products - 1
        if label_digits and label_digits > 0:
            prod_digits = label_digits
        elif grand_total and grand_total > 0:
            prod_digits = digit_width(max(grand_total, end_seq))
        else:
            prod_digits = digit_width(end_seq)
        boxes_denom = box_total if box_total and box_total > 0 else (
            box_start + groups - 1
        )
        box_w = (
            box_digits
            if box_digits and box_digits > 0
            else digit_width(max(boxes_denom, box_start + groups - 1))
        )

        out_doc = fitz.open()
        t0 = time.time()
        total_boxes = end_group - start_group
        log(
            f"源: {Path(src).name}  共 {groups} 箱 / {file_products} 个二维码  "
            f"每箱={qr_per_box} → 每箱 {sheets_per_box} 张A4  "
            f"前缀={prefix}  产品={product_start}…{end_seq} ({prod_digits}位)  "
            f"箱号={box_start}…{box_start + groups - 1}/{boxes_denom}"
        )

        for gi, g in enumerate(range(start_group, end_group)):
            base = g * group_size
            bc_page = base + qr_per_box
            raw = (src_doc[bc_page].get_text("text") or "").replace("\xa0", " ").strip()
            gs1 = raw.splitlines()[0].strip() if raw else ""
            if gs1.startswith("(00)") and len(gs1) > 4 and gs1[4] != " ":
                gs1 = "(00) " + gs1[4:]
            box_no = box_start + g
            box_label = f"{box_no:0{box_w}d}-{boxes_denom:0{box_w}d}"

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
                    seq = product_start + g * qr_per_box + qi
                    label = f"{prefix}-{seq:0{prod_digits}d}"
                    insert_label(
                        page, label, x + QR_W / 2, y + QR_H + 7.0, font, fontname
                    )

                _draw_barcodes(
                    page, src_doc, bc_page, gs1, box_label, font, fontname
                )
                if crop_marks:
                    _draw_crop_marks(page)

            if (gi + 1) % 10 == 0 or gi == 0 or gi + 1 == total_boxes:
                elapsed = time.time() - t0
                rate = (gi + 1) / elapsed if elapsed > 0 else 0
                eta = (total_boxes - gi - 1) / rate if rate > 0 else 0
                log(
                    f"  [{gi + 1}/{total_boxes}] 箱{g + 1} "
                    f"产品 {g * qr_per_box + 1}-{(g + 1) * qr_per_box}  "
                    f"{elapsed:.0f}s elapsed, ETA {eta:.0f}s"
                )

        if out is None:
            buf = io.BytesIO()
            out_doc.save(buf, deflate=True, garbage=3)
            out_doc.close()
            log(f"完成(内存) {time.time() - t0:.0f}s")
            return buf.getvalue()

        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                tmp = out.with_name(out.stem + f"_{int(time.time())}.pdf.tmp")
        log(f"写入 {tmp} …")
        # garbage=1 比 3 快很多，大文件写盘可省数分钟
        out_doc.save(tmp, deflate=True, garbage=1)
        out_doc.close()
        final = out
        try:
            if final.exists():
                final.unlink()
            tmp.rename(final)
        except OSError:
            final = out.with_name(f"{out.stem}_{int(time.time())}{out.suffix}")
            tmp.rename(final)
            log(f"原路径被占用，已另存为: {final.name}")
        log(
            f"完成: {final}  ({final.stat().st_size / 1024 / 1024:.1f} MB, "
            f"{time.time() - t0:.0f}s)"
        )
        return final
    finally:
        src_doc.close()


def merge_pdfs(parts: list[Path], out: Path, chunk: int = 40) -> Path:
    """按顺序合并多个 PDF。分片过多时先合并成中间文件，降低内存峰值。"""
    if not parts:
        raise ValueError("没有可合并的分片")
    out.parent.mkdir(parents=True, exist_ok=True)

    def _merge_list(files: list[Path], dest: Path) -> Path:
        merged = fitz.open()
        try:
            for p in files:
                with fitz.open(p) as doc:
                    merged.insert_pdf(doc)
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            merged.save(tmp, deflate=True, garbage=1)
        finally:
            merged.close()
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                dest = dest.with_name(f"{dest.stem}_{int(time.time())}{dest.suffix}")
        tmp.rename(dest)
        return dest

    if len(parts) <= chunk:
        return _merge_list(parts, out)

    mid_dir = out.parent / f"_merge_{out.stem}"
    mid_dir.mkdir(exist_ok=True)
    mids: list[Path] = []
    try:
        for i in range(0, len(parts), chunk):
            batch = parts[i : i + chunk]
            mid = mid_dir / f"mid_{i // chunk:04d}.pdf"
            mids.append(_merge_list(batch, mid))
        return _merge_list(mids, out)
    finally:
        shutil.rmtree(mid_dir, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="N二维码+1条码 → 多页A4 拼版")
    ap.add_argument("input", type=Path, help="源 PDF")
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--prefix", type=str, default="406-078")
    ap.add_argument(
        "--qr-per-box",
        type=int,
        default=0,
        help="每箱对应几个二维码；0=自动识别（扫到第一条码页）",
    )
    ap.add_argument("--start-group", type=int, default=0)
    ap.add_argument("--max-groups", type=int, default=None)
    ap.add_argument("--digits", type=int, default=0, help="产品编号位数; 0=自动")
    ap.add_argument(
        "--product-start",
        type=int,
        default=1,
        help="本文件第一个产品编号（多文件续编：上一份末号+1）",
    )
    ap.add_argument(
        "--grand-total",
        type=int,
        default=0,
        help="整单产品总数（用于补零位数，如 176400→6位）",
    )
    ap.add_argument(
        "--box-start",
        type=int,
        default=1,
        help="本文件第一箱箱号（多文件续编）",
    )
    ap.add_argument(
        "--box-total",
        type=int,
        default=0,
        help="整单总箱数（箱号分母；0=按本文件推算）",
    )
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
        product_start=args.product_start,
        grand_total=args.grand_total or None,
        box_start=args.box_start,
        box_total=args.box_total or None,
    )


if __name__ == "__main__":
    main()
