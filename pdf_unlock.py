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

    raw_pw = "" if password is None else str(password)
    pw = raw_pw.strip()  # 粘贴时常见首尾空格

    doc = fitz.open(str(src))
    try:
        if doc.is_encrypted:
            # PyMuPDF: 返回权限位整数，0=失败；旧版也可能是 bool
            ok = doc.authenticate(pw)
            if not ok and raw_pw and raw_pw != pw:
                ok = doc.authenticate(raw_pw)
            if not ok and pw:
                ok = doc.authenticate("")  # 少数文件空用户密码即可
            if not ok:
                raise ValueError(
                    "密码错误，或无法解密此文件。"
                    "请确认是「打开密码」而非仅打印限制；"
                    "也可留空再试一次。"
                )

        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            doc.save(
                str(dst),
                encryption=fitz.PDF_ENCRYPT_NONE,
                deflate=True,
                garbage=3,
                clean=True,
            )
        except Exception:
            doc.save(
                str(dst),
                encryption=fitz.PDF_ENCRYPT_NONE,
                deflate=True,
                garbage=1,
            )
    finally:
        doc.close()

    # 校验输出确实可打开且未加密
    check = fitz.open(str(dst))
    try:
        if check.is_encrypted:
            raise ValueError("写出后仍显示加密，请换用本机 Adobe/WPS 另存或联系技术支持")
    finally:
        check.close()

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
