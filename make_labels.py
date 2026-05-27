"""
条码标签 A4 排版 (与 Illustrator 导出的 12_ai.pdf 网格一致)

输入:
  - 多页: 11_ai.pdf (每页 1 个标签, 如 178 页) -> 按顺序排进 A4 每页 6 个
  - 单页: 复制同一标签 N 次

输出: A4 (210x297mm), 2 列 x 3 行, 虚线网格与 12_ai.pdf 一致

用法:
    python make_labels.py 11_ai.pdf
    python make_labels.py 11_ai.pdf 90 -o GC-259_lt12.pdf
    python make_labels.py 11_ai.pdf 178 -o output.pdf
"""

from __future__ import annotations

import argparse
import io
from dataclasses import dataclass
from pathlib import Path

import fitz
from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import ContentStream
from reportlab.lib.pagesizes import A4 as RL_A4
from reportlab.pdfgen import canvas as rl_canvas


def _matmul(a: list[float], b: list[float]) -> list[float]:
    """PDF 仿射矩阵相乘 [a b c d e f] 表示 [[a b 0],[c d 0],[e f 1]]."""
    return [
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    ]


def _apply(m: list[float], x: float, y: float) -> tuple[float, float]:
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def compute_content_bbox(page, reader) -> tuple[float, float, float, float]:
    """遍历内容流, 计算实际绘图内容的边界框 (x0, y0, x1, y1).

    覆盖: 矩形 re, 路径 m/l/c/v/y, XObject Do (按其 BBox).
    自动忽略覆盖整张页面的"背景/裁切框"矩形, 避免污染 bbox.
    """
    media = page.mediabox
    mx0 = float(media.left)
    my0 = float(media.bottom)
    mx1 = float(media.right)
    my1 = float(media.top)
    media_area = (mx1 - mx0) * (my1 - my0)

    cs = ContentStream(page.get_contents(), reader)
    ctm_stack: list[list[float]] = [[1, 0, 0, 1, 0, 0]]

    text_matrix: list[float] = [1, 0, 0, 1, 0, 0]
    text_line_matrix: list[float] = [1, 0, 0, 1, 0, 0]
    in_text = False

    x_min = y_min = float("inf")
    x_max = y_max = float("-inf")

    resources = page.get("/Resources", {}) or {}
    xobjects = resources.get("/XObject", {}) if resources else {}

    def add_point(tx: float, ty: float) -> None:
        nonlocal x_min, y_min, x_max, y_max
        if tx < x_min:
            x_min = tx
        if tx > x_max:
            x_max = tx
        if ty < y_min:
            y_min = ty
        if ty > y_max:
            y_max = ty

    def add_local(px: float, py: float) -> None:
        tx, ty = _apply(ctm_stack[-1], px, py)
        add_point(tx, ty)

    def is_fullpage_rect(tpts: list[tuple[float, float]]) -> bool:
        xs = [p[0] for p in tpts]
        ys = [p[1] for p in tpts]
        rx0, rx1 = min(xs), max(xs)
        ry0, ry1 = min(ys), max(ys)
        area = (rx1 - rx0) * (ry1 - ry0)
        if media_area <= 0 or area < 0.85 * media_area:
            return False
        return (
            rx0 <= mx0 + 1
            and ry0 <= my0 + 1
            and rx1 >= mx1 - 1
            and ry1 >= my1 - 1
        )

    for operands, op in cs.operations:
        op_str = op.decode() if isinstance(op, bytes) else str(op)
        try:
            if op_str == "q":
                ctm_stack.append(list(ctm_stack[-1]))
            elif op_str == "Q":
                if len(ctm_stack) > 1:
                    ctm_stack.pop()
            elif op_str == "cm":
                new = [float(o) for o in operands]
                ctm_stack[-1] = _matmul(new, ctm_stack[-1])
            elif op_str == "re":
                x, y, w, h = [float(o) for o in operands]
                pts = ((x, y), (x + w, y), (x, y + h), (x + w, y + h))
                tpts = [_apply(ctm_stack[-1], px, py) for px, py in pts]
                if is_fullpage_rect(tpts):
                    continue
                for tx, ty in tpts:
                    add_point(tx, ty)
            elif op_str == "m" or op_str == "l":
                add_local(float(operands[0]), float(operands[1]))
            elif op_str == "c":
                pts = [float(o) for o in operands]
                for i in range(0, 6, 2):
                    add_local(pts[i], pts[i + 1])
            elif op_str == "v" or op_str == "y":
                pts = [float(o) for o in operands]
                for i in range(0, 4, 2):
                    add_local(pts[i], pts[i + 1])
            elif op_str == "Do":
                name = operands[0]
                if xobjects and name in xobjects:
                    xobj = xobjects[name].get_object()
                    bbox = xobj.get("/BBox")
                    if bbox is not None and len(bbox) == 4:
                        bx0, by0, bx1, by1 = [float(v) for v in bbox]
                        pts = (
                            (bx0, by0), (bx1, by0), (bx0, by1), (bx1, by1)
                        )
                        tpts = [_apply(ctm_stack[-1], px, py) for px, py in pts]
                        if is_fullpage_rect(tpts):
                            continue
                        for tx, ty in tpts:
                            add_point(tx, ty)
                    else:
                        sub = xobj.get("/Subtype")
                        if sub == "/Image":
                            pts = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0))
                            tpts = [
                                _apply(ctm_stack[-1], px, py) for px, py in pts
                            ]
                            if not is_fullpage_rect(tpts):
                                for tx, ty in tpts:
                                    add_point(tx, ty)
            elif op_str == "BT":
                in_text = True
                text_matrix = [1, 0, 0, 1, 0, 0]
                text_line_matrix = [1, 0, 0, 1, 0, 0]
            elif op_str == "ET":
                in_text = False
            elif op_str == "Tm":
                new_tm = [float(o) for o in operands]
                text_matrix = list(new_tm)
                text_line_matrix = list(new_tm)
                combined = _matmul(text_matrix, ctm_stack[-1])
                add_point(combined[4], combined[5])
            elif op_str == "Td" or op_str == "TD":
                tx_off = float(operands[0])
                ty_off = float(operands[1])
                shift = [1, 0, 0, 1, tx_off, ty_off]
                text_line_matrix = _matmul(shift, text_line_matrix)
                text_matrix = list(text_line_matrix)
                combined = _matmul(text_matrix, ctm_stack[-1])
                add_point(combined[4], combined[5])
            elif op_str == "T*":
                shift = [1, 0, 0, 1, 0, 0]
                text_line_matrix = _matmul(shift, text_line_matrix)
                text_matrix = list(text_line_matrix)
                combined = _matmul(text_matrix, ctm_stack[-1])
                add_point(combined[4], combined[5])
            elif op_str in ("Tj", "TJ", "'", '"'):
                if in_text:
                    combined = _matmul(text_matrix, ctm_stack[-1])
                    add_point(combined[4], combined[5])
        except Exception:
            continue

    if x_min == float("inf"):
        return (mx0, my0, mx1, my1)

    x_min = max(x_min, mx0)
    y_min = max(y_min, my0)
    x_max = min(x_max, mx1)
    y_max = min(y_max, my1)
    return (x_min, y_min, x_max, y_max)


def compute_content_bbox_pymupdf(
    pdf_path: Path, page_index: int
) -> tuple[float, float, float, float]:
    """用 PyMuPDF 检测真实内容边界, 转成 pypdf 的 PDF 原生坐标 (左下角原点, Y 向上).

    PyMuPDF 默认坐标系是左上角原点 (Y 向下), 需要按 page_h - y 翻转.
    """
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_index]
        media = page.rect
        page_h = media.height
        media_area = abs(media)

        union: fitz.Rect | None = None

        def merge(r: fitz.Rect) -> None:
            nonlocal union
            if r.is_empty or r.is_infinite:
                return
            if media_area > 0 and abs(r) >= 0.85 * media_area:
                return
            union = r if union is None else (union | r)

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") == 0:
                merge(fitz.Rect(block["bbox"]))

        for xref, *_ in page.get_images(full=True):
            try:
                for rect in page.get_image_rects(xref):
                    merge(rect)
            except Exception:
                pass

        for d in page.get_drawings():
            merge(fitz.Rect(d["rect"]))

        if union is None or union.is_empty:
            union = media

        union &= media

        # PyMuPDF (top-left, Y down) -> PDF (bottom-left, Y up)
        pdf_x0 = union.x0
        pdf_x1 = union.x1
        pdf_y0 = page_h - union.y1
        pdf_y1 = page_h - union.y0
        return (pdf_x0, pdf_y0, pdf_x1, pdf_y1)
    finally:
        doc.close()


def get_content_bbox(
    pdf_path: Path,
    page_index: int,
    pypdf_page=None,
    pypdf_reader=None,
) -> tuple[float, float, float, float]:
    """优先 PyMuPDF, 失败时回退 pypdf 内容流解析。"""
    try:
        return compute_content_bbox_pymupdf(pdf_path, page_index)
    except Exception:
        if pypdf_page is not None and pypdf_reader is not None:
            return compute_content_bbox(pypdf_page, pypdf_reader)
        raise


A4_WIDTH_PT, A4_HEIGHT_PT = RL_A4
MM_TO_PT = 72.0 / 25.4

def check_pdf_file(path: Path) -> None:
    """确认文件存在且为标准 PDF (非 WPS %TSD- 格式)。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到文件: {path}")
    with open(path, "rb") as f:
        header = f.read(8)
    if header.startswith(b"%PDF-"):
        return
    if header.startswith(b"%TSD-"):
        raise ValueError(
            f"{path.name} 是 WPS 私有格式 (TSD), 不是真正的 PDF。\n"
            "  请用 Illustrator: 文件 → 存储为 → Adobe PDF 重新导出,\n"
            "  或从微信重新下载原始 PDF (不要让 WPS 自动打开/保存)。\n"
            "  导出后文件头应为 %PDF-1.x"
        )
    raise ValueError(
        f"{path.name} 不是有效 PDF (文件头: {header!r})。"
        f" 请用 Illustrator 导出标准 PDF。"
    )


COLS = 2
ROWS = 3
PER_PAGE = COLS * ROWS


# 从 12_ai.pdf (Illustrator 导出) 提取的网格参数
@dataclass(frozen=True)
class GridSpec:
    """与参考 PDF 12_ai.pdf 一致的 A4 虚线网格。"""

    margin_left: float = 0.0
    margin_bottom: float = 61.6123
    margin_top: float = 60.2235  # 841.89 - 781.6665
    cell_w: float = 297.6377
    cell_h: float = 240.0
    dash_on: float = 11.761
    dash_off: float = 11.915
    line_width: float = 0.5

    @property
    def grid_left(self) -> float:
        return self.margin_left

    @property
    def grid_bottom(self) -> float:
        return self.margin_bottom

    @property
    def grid_width(self) -> float:
        return self.cell_w * COLS

    @property
    def grid_height(self) -> float:
        return self.cell_h * ROWS

    @property
    def grid_top(self) -> float:
        return self.grid_bottom + self.grid_height

    def cell_top_y(self, row_from_top: int) -> float:
        """row_from_top: 0=最上行, 2=最下行 (PDF 坐标, 格子上沿)。"""
        return self.grid_bottom + (ROWS - row_from_top) * self.cell_h

    def cell_left_x(self, col: int) -> float:
        return self.grid_left + col * self.cell_w


GRID = GridSpec()


def make_dashed_grid_page_bytes(spec: GridSpec = GRID) -> bytes:
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=RL_A4)
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(spec.line_width)
    c.setDash(spec.dash_on, spec.dash_off)

    g = spec
    c.rect(g.grid_left, g.grid_bottom, g.grid_width, g.grid_height, stroke=1, fill=0)

    x_mid = g.grid_left + g.cell_w
    c.line(x_mid, g.grid_bottom, x_mid, g.grid_top)

    for i in range(1, ROWS):
        y = g.grid_bottom + i * g.cell_h
        c.line(g.grid_left, y, g.grid_left + g.grid_width, y)

    c.showPage()
    c.save()
    return buf.getvalue()


def _label_transform(
    spec: GridSpec,
    src_bbox: tuple[float, float, float, float],
    row_from_top: int,
    col: int,
    align: str = "center",
    rotate: int = 0,
    max_scale: float | None = 1.0,
    cell_padding: float = 0.0,
) -> Transformation:
    """把 src_bbox 区域的内容塞进指定格子, 等比缩放, 可选旋转.

    max_scale: 最大缩放倍数; 默认 1.0 = 1:1 不放大, 只缩小过大的内容.
    """
    x0, y0, x1, y1 = src_bbox
    bw = x1 - x0
    bh = y1 - y0

    rot = rotate % 360
    if rot in (90, 270):
        rotated_w, rotated_h = bh, bw
    else:
        rotated_w, rotated_h = bw, bh

    usable_w = spec.cell_w - 2 * cell_padding
    usable_h = spec.cell_h - 2 * cell_padding
    scale = min(usable_w / rotated_w, usable_h / rotated_h)
    if max_scale is not None:
        scale = min(scale, max_scale)

    new_w = rotated_w * scale
    new_h = rotated_h * scale

    cell_top = spec.cell_top_y(row_from_top)
    cell_left = spec.cell_left_x(col)

    if align == "top-left":
        tx = cell_left + cell_padding
        ty = cell_top - cell_padding - new_h
    else:
        tx = cell_left + cell_padding + (usable_w - new_w) / 2.0
        ty = cell_top - cell_padding - new_h - (usable_h - new_h) / 2.0

    transform = Transformation().translate(-x0, -y0)
    if rot != 0:
        transform = transform.rotate(rot)
        if rot == 90:
            transform = transform.translate(bh, 0)
        elif rot == 180:
            transform = transform.translate(bw, bh)
        elif rot == 270:
            transform = transform.translate(0, bw)
    transform = transform.scale(scale, scale).translate(tx, ty)
    return transform


def make_grid_pdf(
    src_pdf: Path,
    out_pdf: Path,
    count: int | None = None,
    start_page: int = 1,
    spec: GridSpec = GRID,
    draw_grid: bool = True,
    align: str = "center",
    rotate: int | None = None,
    fit: str = "content",
    src_bbox_override: tuple[float, float, float, float] | None = None,
    max_scale: float | None = 1.0,
    cell_padding: float = 0.0,
) -> None:
    """
    fit:
      - "content"  按内容实际边界 (PyMuPDF), 默认 1:1 不放大
      - "media"    按 MediaBox 整张缩放

    max_scale: None=可任意放大填满; 1.0=1:1 原尺寸 (默认).
    """
    check_pdf_file(src_pdf)
    reader = PdfReader(str(src_pdf))
    if reader.is_encrypted:
        reader.decrypt("")
    total_src = len(reader.pages)
    if total_src == 0:
        raise ValueError(f"源 PDF 没有任何页面: {src_pdf}")

    if count is None:
        count = total_src - (start_page - 1)
    if count <= 0:
        raise ValueError("count 必须大于 0")

    sample_idx = 0 if total_src == 1 else (start_page - 1)
    sample_page = reader.pages[sample_idx]
    media = sample_page.mediabox
    media_w = float(media.width)
    media_h = float(media.height)

    if src_bbox_override is not None:
        bbox = src_bbox_override
    elif fit == "content":
        bbox = get_content_bbox(
            src_pdf, sample_idx, sample_page, reader
        )
    else:
        bbox = (
            float(media.left),
            float(media.bottom),
            float(media.right),
            float(media.top),
        )

    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]

    if rotate is None:
        rotate = 0

    template_page = None
    if draw_grid:
        template_bytes = make_dashed_grid_page_bytes(spec)
        template_page = PdfReader(io.BytesIO(template_bytes)).pages[0]

    writer = PdfWriter()
    pages_needed = (count + PER_PAGE - 1) // PER_PAGE

    for out_idx in range(pages_needed):
        a4_page = PageObject.create_blank_page(
            width=A4_WIDTH_PT, height=A4_HEIGHT_PT
        )
        if template_page is not None:
            a4_page.merge_page(template_page)

        for slot in range(PER_PAGE):
            label_idx = out_idx * PER_PAGE + slot
            if label_idx >= count:
                break

            row_from_top = slot // COLS
            col = slot % COLS

            if total_src == 1:
                src_page = reader.pages[0]
                page_bbox = bbox
            else:
                src_page_idx = (start_page - 1) + label_idx
                if src_page_idx >= total_src:
                    raise ValueError(
                        f"标签 {label_idx + 1} 需要源 PDF 第 {src_page_idx + 1} 页, "
                        f"但源文件只有 {total_src} 页"
                    )
                src_page = reader.pages[src_page_idx]
                if src_bbox_override is not None:
                    page_bbox = src_bbox_override
                elif fit == "content":
                    page_bbox = get_content_bbox(
                        src_pdf, src_page_idx, src_page, reader
                    )
                else:
                    m = src_page.mediabox
                    page_bbox = (
                        float(m.left),
                        float(m.bottom),
                        float(m.right),
                        float(m.top),
                    )

            transform = _label_transform(
                spec,
                page_bbox,
                row_from_top,
                col,
                align=align,
                rotate=rotate,
                max_scale=max_scale,
                cell_padding=cell_padding,
            )
            a4_page.merge_transformed_page(src_page, transform)

        writer.add_page(a4_page)

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out_pdf, "wb") as f:
            writer.write(f)
    except PermissionError:
        raise PermissionError(
            f"无法写入 {out_pdf}，文件可能正被 WPS/Adobe 打开。"
            f" 请关闭后重试，或换输出名: -o output_new.pdf"
        ) from None

    rw = bh if rotate in (90, 270) else bw
    rh = bw if rotate in (90, 270) else bh
    usable_w = spec.cell_w - 2 * cell_padding
    usable_h = spec.cell_h - 2 * cell_padding
    scale = min(usable_w / rw, usable_h / rh)
    if max_scale is not None:
        scale = min(scale, max_scale)
    ms = "无限制" if max_scale is None else str(max_scale)

    print(
        f"已生成: {out_pdf}\n"
        f"  标签数: {count}, 输出页数: {pages_needed} (每页 {PER_PAGE} 个)\n"
        f"  源: {src_pdf.name} ({total_src} 页)\n"
        f"  MediaBox: {media_w:.2f} x {media_h:.2f} pt\n"
        f"  内容 bbox (PyMuPDF): ({bbox[0]:.2f}, {bbox[1]:.2f}) - "
        f"({bbox[2]:.2f}, {bbox[3]:.2f})  = {bw:.2f} x {bh:.2f} pt\n"
        f"  fit={fit}, 旋转 {rotate} 度, max_scale={ms}\n"
        f"  格子尺寸: {spec.cell_w:.2f} x {spec.cell_h:.2f} pt\n"
        f"  实际缩放: {scale:.4f}  缩放后: {rw*scale:.2f} x {rh*scale:.2f} pt"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="标签 PDF -> A4 每页 6 个 (网格与 12_ai.pdf 一致)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", type=Path, help="源 PDF (单页或多页, 每页 1 标签)")
    parser.add_argument(
        "count",
        type=int,
        nargs="?",
        default=None,
        help="标签数量 (默认=源 PDF 全部页数)",
    )
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出 PDF")
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="从源 PDF 第几页开始 (1-based, 默认 1)",
    )
    parser.add_argument(
        "--align",
        choices=("top-left", "center"),
        default="center",
        help="标签在格子内对齐 (默认 center)",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        choices=(0, 90, 180, 270),
        default=None,
        help="标签旋转角度 (默认自动: 内容和格子方向不一致时旋转 90)",
    )
    parser.add_argument(
        "--fit",
        choices=("content", "media"),
        default="content",
        help="content=按内容边界 (默认), media=按 MediaBox",
    )
    parser.add_argument(
        "--fill",
        action="store_true",
        help="放大填满格子 (默认 1:1 不放大, 只缩小)",
    )
    parser.add_argument(
        "--cell-padding",
        type=float,
        default=0.0,
        help="格子内边距 (pt, 默认 0)",
    )
    parser.add_argument(
        "--src-bbox",
        type=str,
        default=None,
        help="手动指定源 PDF 取景框 'x0,y0,x1,y1' (pt), 会覆盖 fit 自动检测",
    )
    parser.add_argument("--no-grid", action="store_true", help="不绘制虚线")
    args = parser.parse_args()

    reader = PdfReader(str(args.input))
    default_count = len(reader.pages) - (args.start - 1) if len(reader.pages) > 1 else args.count
    count = args.count if args.count is not None else default_count

    if count is None or count <= 0:
        parser.error("请指定 count, 或使用多页源 PDF")

    output = args.output or args.input.with_name(
        f"{args.input.stem}_A4-6up_x{count}.pdf"
    )

    src_bbox_override = None
    if args.src_bbox:
        parts = args.src_bbox.replace("，", ",").split(",")
        if len(parts) != 4:
            parser.error("--src-bbox 必须是 'x0,y0,x1,y1' 4 个数字")
        src_bbox_override = tuple(float(p) for p in parts)  # type: ignore[assignment]

    max_scale = None if args.fill else 1.0
    if args.fit == "media" and not args.fill:
        max_scale = 1.0

    make_grid_pdf(
        args.input,
        output,
        count=count,
        start_page=args.start,
        draw_grid=not args.no_grid,
        align=args.align,
        rotate=args.rotate,
        fit=args.fit,
        src_bbox_override=src_bbox_override,
        max_scale=max_scale,
        cell_padding=args.cell_padding,
    )


if __name__ == "__main__":
    main()
