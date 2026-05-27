"""
检查参考 PDF 的关键参数:
  - 页面尺寸 (mm)
  - 是否有虚线 / 线段 / 矩形 (从内容流中找)
  - 把每页的内容流前几百字节打印出来, 方便分析虚线坐标和样式

用法:
    python inspect_ref.py 12.pdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ContentStream

MM_PER_PT = 25.4 / 72.0


def main(path: Path) -> None:
    print(f"=== 文件: {path} ===")
    if not path.exists():
        print(f"ERROR: 文件不存在")
        return

    with open(path, "rb") as f:
        header = f.read(8)
    print(f"文件头 (前 8 字节): {header!r}")

    if header.startswith(b"%PDF-"):
        print("OK: 是标准 PDF")
    elif header.startswith(b"%TSD-"):
        print("ERROR: 这是 WPS 私有格式 (TSD), 不是真正的 PDF!")
        print("       请用 WPS 打开后 '文件 -> 输出为PDF' 重新保存,")
        print("       或者重新从微信下载原始 PDF (不要让 WPS 自动处理)")
        return
    else:
        print(f"WARNING: 未知文件格式, 不是 PDF")
        return

    reader = PdfReader(str(path))
    print(f"页数: {len(reader.pages)}")
    if reader.is_encrypted:
        print("WARNING: PDF 是加密的, 尝试空密码解密")
        reader.decrypt("")

    for i, page in enumerate(reader.pages[:2]):
        box = page.mediabox
        w_pt = float(box.width)
        h_pt = float(box.height)
        print(f"\n--- 第 {i + 1} 页 ---")
        print(
            f"MediaBox: {float(box.left):.2f}, {float(box.bottom):.2f}, "
            f"{float(box.right):.2f}, {float(box.top):.2f}  (pt)"
        )
        print(f"页面尺寸: {w_pt:.2f} x {h_pt:.2f} pt"
              f"  =  {w_pt * MM_PER_PT:.2f} x {h_pt * MM_PER_PT:.2f} mm")

        try:
            cs = ContentStream(page.get_contents(), reader)
        except Exception as e:
            print(f"无法解析内容流: {e}")
            continue

        ops = cs.operations
        print(f"内容流操作数: {len(ops)}")

        dash_ops = []
        line_ops = []
        rect_ops = []
        move_ops = []
        line_width_ops = []
        cm_ops = []
        for operands, op in ops:
            try:
                op_str = op.decode() if isinstance(op, bytes) else str(op)
            except Exception:
                op_str = repr(op)
            if op_str == "d":
                dash_ops.append(operands)
            elif op_str == "l":
                line_ops.append(operands)
            elif op_str == "m":
                move_ops.append(operands)
            elif op_str == "re":
                rect_ops.append(operands)
            elif op_str == "w":
                line_width_ops.append(operands)
            elif op_str == "cm":
                cm_ops.append(operands)

        print(f"虚线设置 d 次数: {len(dash_ops)}, 样例: {dash_ops[:5]}")
        print(f"线宽 w 次数: {len(line_width_ops)}, 样例: {line_width_ops[:5]}")
        print(f"moveto m 次数: {len(move_ops)}, 样例: {move_ops[:6]}")
        print(f"lineto l 次数: {len(line_ops)}, 样例: {line_ops[:6]}")
        print(f"rect re 次数: {len(rect_ops)}, 样例: {rect_ops[:6]}")
        print(f"cm 次数: {len(cm_ops)}, 前 6 个: {cm_ops[:6]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python inspect_ref.py <reference.pdf>")
        sys.exit(1)
    main(Path(sys.argv[1]))
