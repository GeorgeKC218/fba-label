"""
PDF 解锁: 用密码打开加密 PDF, 导出无加密副本.

用法:
    python pdf_unlock.py locked.pdf -p 密码
    python pdf_unlock.py locked.pdf -p 密码 -o unlocked.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def is_encrypted(path: Path) -> bool:
    doc = fitz.open(str(path))
    try:
        return bool(doc.is_encrypted)
    finally:
        doc.close()


def unlock_pdf(
    src: Path,
    dst: Path,
    password: str = "",
) -> Path:
    """用 password 解密 src, 保存无加密副本到 dst.

    password 可为空字符串 (部分文件仅 owner 密码 / 空用户密码).
    """
    if not src.exists():
        raise FileNotFoundError(f"找不到文件: {src}")

    with open(src, "rb") as f:
        header = f.read(8)
    if header.startswith(b"%TSD-"):
        raise ValueError(
            f"{src.name} 是 WPS 私有格式 (TSD), 不是真正的 PDF。"
            "请先用 Illustrator/Adobe 导出标准 PDF。"
        )
    if not header.startswith(b"%PDF-"):
        raise ValueError(f"{src.name} 不是有效 PDF (文件头: {header!r})")

    doc = fitz.open(str(src))
    try:
        if doc.is_encrypted:
            # authenticate: True=成功, False=失败
            ok = doc.authenticate(password)
            if not ok:
                raise ValueError("密码错误, 或无法解密此文件")

        dst.parent.mkdir(parents=True, exist_ok=True)
        # encryption=fitz.PDF_ENCRYPT_NONE 写出无加密 PDF
        doc.save(
            str(dst),
            encryption=fitz.PDF_ENCRYPT_NONE,
            deflate=True,
            garbage=3,
        )
    finally:
        doc.close()

    return dst


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF 解锁 (需正确密码)")
    parser.add_argument("input", type=Path, help="加密的源 PDF")
    parser.add_argument(
        "-p",
        "--password",
        default="",
        help="打开密码 (默认空密码)",
    )
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    out = args.output or args.input.with_name(f"{args.input.stem}_unlocked.pdf")
    unlock_pdf(args.input, out, password=args.password)
    print(f"已解锁: {out}")


if __name__ == "__main__":
    main()
