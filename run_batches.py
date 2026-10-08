"""
按 batches.json 配置, 从多页源 PDF 批量生成多个 A4 排版 PDF.

用法:
    python run_batches.py
    python run_batches.py my_batches.json
    python run_batches.py --input 11_ai.pdf --batch "IT12:1-90,IT30:91-107,IT50:108-178"

命令行快速指定 (不写 json):
    --batch 格式: 名称:起始页-结束页, 名称:起始页-结束页, ...
    页码均为 1-based 闭区间 [start, end]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from make_labels import check_pdf_file, make_grid_pdf


def parse_batch_spec(spec: str) -> dict:
    """解析 'IT12:1-90' -> {name, start, count, output}."""
    m = re.match(r"^(.+?):(\d+)-(\d+)$", spec.strip())
    if not m:
        raise ValueError(f"批次格式错误: {spec!r}, 应为 名称:起始-结束, 如 IT12:1-90")
    name, start_s, end_s = m.group(1), int(m.group(2)), int(m.group(3))
    if end_s < start_s:
        raise ValueError(f"结束页不能小于起始页: {spec}")
    count = end_s - start_s + 1
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    return {
        "name": name,
        "start": start_s,
        "count": count,
        "output": f"{safe}.pdf",
    }


def load_config(path: Path) -> tuple[Path, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    input_pdf = Path(data["input"])
    batches = data["batches"]
    for b in batches:
        if "output" not in b:
            b["output"] = f"{b.get('name', 'out')}.pdf"
    return input_pdf, batches


def run_batches(
    input_pdf: Path,
    batches: list[dict],
    *,
    output_dir: Path | None = None,
    align: str = "center",
    fill: bool = False,
    no_grid: bool = False,
    per_page: int = 4,
    trim_border: bool = False,
    compact: bool = False,
    gutter: float | None = None,
    quiet: bool = False,
) -> list[Path]:
    """生成批次 PDF, 返回输出文件路径列表。"""
    check_pdf_file(input_pdf)

    max_scale = None if fill else 1.0
    if not quiet:
        print(f"源文件: {input_pdf.resolve()}")
        print(f"共 {len(batches)} 个批次, 每页 {per_page} 个\n")

    outputs: list[Path] = []
    for i, b in enumerate(batches, 1):
        name = b.get("name", f"batch{i}")
        start = int(b["start"])
        count = int(b["count"])
        out = Path(b["output"])
        if output_dir is not None:
            out = output_dir / out.name

        if not quiet:
            print(f"{'=' * 50}")
            print(f"[{i}/{len(batches)}] {name}")
            print(f"  源页: 第 {start} - {start + count - 1} 页 ({count} 个标签)")
            print(f"  输出: {out}")
            print()

        make_grid_pdf(
            input_pdf,
            out,
            count=count,
            start_page=start,
            per_page=per_page,
            draw_grid=not no_grid,
            align=align,
            max_scale=max_scale,
            trim_border=trim_border,
            compact=compact,
            gutter=gutter,
        )
        outputs.append(out)
        if not quiet:
            print()

    if not quiet:
        print("全部完成.")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="批量生成多个 A4 排版 PDF")
    parser.add_argument(
        "config",
        nargs="?",
        default="batches.json",
        help="批次配置 JSON (默认 batches.json)",
    )
    parser.add_argument("--input", type=Path, help="覆盖配置中的源 PDF")
    parser.add_argument(
        "--batch",
        type=str,
        help='命令行批次, 如 "IT12:1-90,IT30:91-107,IT50:108-178"',
    )
    parser.add_argument("--fill", action="store_true", help="放大填满格子")
    parser.add_argument("--no-grid", action="store_true", help="不画虚线")
    parser.add_argument(
        "--per-page",
        type=int,
        choices=(2, 4, 6, 9),
        default=4,
        help="每页标签数: 4=2x2 (默认), 6=2x3, 9=3x3, 2=2x1",
    )
    parser.add_argument(
        "--align",
        choices=("center", "top-left"),
        default="center",
    )
    parser.add_argument(
        "--trim-border",
        action="store_true",
        help="裁掉源标签外黑框, 再按比例放进虚线格",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="自适应虚线格+保留黑框+两两贴中间",
    )
    parser.add_argument(
        "--gutter",
        type=float,
        nargs="?",
        const=6.0,
        default=None,
        help="留缝版空隙宽度 (pt), 默认 6; 与 --compact 互斥",
    )
    args = parser.parse_args()

    if args.compact and args.gutter is not None:
        parser.error("--compact 与 --gutter 不能同时使用")

    if args.batch:
        if not args.input:
            parser.error("使用 --batch 时必须同时指定 --input")
        batches = [parse_batch_spec(s) for s in args.batch.split(",")]
        input_pdf = args.input
    else:
        config_path = Path(args.config)
        if not config_path.exists():
            parser.error(f"找不到配置: {config_path}")
        input_pdf, batches = load_config(config_path)
        if args.input:
            input_pdf = args.input

    run_batches(
        input_pdf,
        batches,
        align=args.align,
        fill=args.fill,
        no_grid=args.no_grid,
        per_page=args.per_page,
        trim_border=args.trim_border,
        compact=args.compact,
        gutter=args.gutter,
    )


if __name__ == "__main__":
    main()
