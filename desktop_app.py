"""
FBA 条码 A4 排版 — 本地桌面版 (无需浏览器)

运行:
    python desktop_app.py

打包成 exe (需先 pip install pyinstaller):
    pyinstaller --onefile --windowed --name "FBA条码排版" desktop_app.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import fitz

from make_labels import check_pdf_file
from run_batches import run_batches

# 列: 名称, 起始页, 结束页, 输出文件名, 启用(填「是」或「否」)
DEFAULT_ROWS = [
    ("GC-259_It12", 1, 90, "GC-259_It12.pdf", "是"),
    ("GC-230_It30", 91, 107, "GC-230_It30.pdf", "是"),
    ("GC-258_It50", 108, 178, "GC-258_It50.pdf", "是"),
]


class LabelApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("FBA 条码 A4 排版")
        self.geometry("720x520")
        self.minsize(640, 400)

        self.input_path = tk.StringVar()
        self.output_dir = tk.StringVar(
            value=str(Path.home() / "Desktop" / "fba_output")
        )
        self.status = tk.StringVar(value="请选择源 PDF 文件")
        self.page_count = tk.IntVar(value=0)

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}

        f1 = ttk.LabelFrame(self, text="源文件")
        f1.pack(fill="x", **pad)
        ttk.Entry(f1, textvariable=self.input_path).pack(
            side="left", fill="x", expand=True, padx=4, pady=6
        )
        ttk.Button(f1, text="浏览…", command=self._pick_input).pack(
            side="right", padx=4, pady=6
        )

        f2 = ttk.LabelFrame(self, text="输出文件夹")
        f2.pack(fill="x", **pad)
        ttk.Entry(f2, textvariable=self.output_dir).pack(
            side="left", fill="x", expand=True, padx=4, pady=6
        )
        ttk.Button(f2, text="浏览…", command=self._pick_output).pack(
            side="right", padx=4, pady=6
        )

        f3 = ttk.LabelFrame(self, text="批次（页码从 1 开始）")
        f3.pack(fill="both", expand=True, **pad)

        cols = ("名称", "起始页", "结束页", "输出文件名", "启用")
        self.tree = ttk.Treeview(f3, columns=cols, show="headings", height=6)
        for c in cols:
            self.tree.heading(c, text=c)
            w = 50 if c == "启用" else (70 if "页" in c else 140)
            self.tree.column(c, width=w, anchor="center" if c != "输出文件名" else "w")
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)

        sb = ttk.Scrollbar(f3, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)

        bf = ttk.Frame(f3)
        bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="添加一行", command=self._add_row).pack(side="left")
        ttk.Button(bf, text="删除选中", command=self._del_row).pack(side="left", padx=4)
        ttk.Button(bf, text="恢复默认 IT12/30/50", command=self._reset_rows).pack(
            side="left", padx=4
        )

        for row in DEFAULT_ROWS:
            self.tree.insert("", "end", values=row)

        opt = ttk.Frame(self)
        opt.pack(fill="x", **pad)
        self.per_page_var = tk.IntVar(value=4)
        ttk.Label(opt, text="每页:").pack(side="left")
        ttk.Radiobutton(opt, text="4个(2×2)", variable=self.per_page_var, value=4).pack(
            side="left"
        )
        ttk.Radiobutton(opt, text="6个(2×3)", variable=self.per_page_var, value=6).pack(
            side="left", padx=4
        )
        ttk.Radiobutton(opt, text="2个", variable=self.per_page_var, value=2).pack(
            side="left", padx=4
        )
        self.align_var = tk.StringVar(value="center")
        ttk.Label(opt, text="  对齐:").pack(side="left", padx=(12, 0))
        ttk.Radiobutton(opt, text="居中", variable=self.align_var, value="center").pack(
            side="left"
        )
        ttk.Radiobutton(
            opt, text="左上", variable=self.align_var, value="top-left"
        ).pack(side="left", padx=8)
        self.fill_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="放大填满格子", variable=self.fill_var).pack(
            side="left", padx=16
        )

        btn = ttk.Frame(self)
        btn.pack(fill="x", **pad)
        ttk.Button(
            btn, text="生成 PDF", command=self._generate, style="Accent.TButton"
        ).pack(side="left", padx=4)
        ttk.Button(btn, text="打开输出文件夹", command=self._open_output).pack(
            side="left"
        )

        ttk.Label(self, textvariable=self.status, foreground="#333").pack(
            anchor="w", padx=12, pady=6
        )

    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(
            title="选择源 PDF",
            filetypes=[("PDF", "*.pdf"), ("All", "*.*")],
        )
        if not p:
            return
        self.input_path.set(p)
        try:
            check_pdf_file(Path(p))
            doc = fitz.open(p)
            n = len(doc)
            doc.close()
            self.page_count.set(n)
            self.status.set(f"已加载: {Path(p).name}，共 {n} 页")
        except Exception as e:
            messagebox.showerror("文件无效", str(e))
            self.page_count.set(0)
            self.status.set("文件无效")

    def _pick_output(self) -> None:
        d = filedialog.askdirectory(title="选择输出文件夹")
        if d:
            self.output_dir.set(d)

    def _add_row(self) -> None:
        n = len(self.tree.get_children()) + 1
        self.tree.insert("", "end", values=(f"批次{n}", 1, 1, f"批次{n}.pdf", "是"))

    def _del_row(self) -> None:
        for iid in self.tree.selection():
            self.tree.delete(iid)

    def _reset_rows(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for row in DEFAULT_ROWS:
            self.tree.insert("", "end", values=row)

    def _collect_batches(self) -> list[dict]:
        total = self.page_count.get()
        if total <= 0:
            raise ValueError("请先选择有效的源 PDF")

        batches: list[dict] = []
        used: list[tuple[int, int]] = []

        for iid in self.tree.get_children():
            v = list(self.tree.item(iid, "values"))
            # 列顺序: 名称, 起始页, 结束页, 输出文件名, 启用
            name = str(v[0]).strip()
            start, end = int(v[1]), int(v[2])
            out = str(v[3]).strip()
            enabled = v[4] if len(v) > 4 else "是"
            if isinstance(enabled, bool):
                enabled = enabled
            elif isinstance(enabled, str):
                enabled = enabled.strip().lower() in (
                    "true", "1", "yes", "是", "y", "on", "✓", "☑"
                )
            else:
                enabled = bool(enabled)
            if not enabled:
                continue
            if not out.lower().endswith(".pdf"):
                out += ".pdf"

            if start < 1 or end < start:
                raise ValueError(f"「{name}」页码无效: {start}-{end}")
            if end > total:
                raise ValueError(f"「{name}」结束页 {end} 超过总页数 {total}")
            for s0, e0 in used:
                if not (end < s0 or start > e0):
                    raise ValueError(f"「{name}」与 {s0}-{e0} 页重叠")
            used.append((start, end))
            batches.append(
                {
                    "name": name,
                    "start": start,
                    "count": end - start + 1,
                    "output": out,
                }
            )

        if not batches:
            raise ValueError("请至少启用一个批次")
        return batches

    def _generate(self) -> None:
        src = Path(self.input_path.get())
        out_dir = Path(self.output_dir.get())
        if not src.is_file():
            messagebox.showwarning("提示", "请先选择源 PDF")
            return
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            batches = self._collect_batches()
            self.status.set("正在生成，请稍候…")
            self.update_idletasks()
            outputs = run_batches(
                src,
                batches,
                output_dir=out_dir,
                align=self.align_var.get(),
                fill=self.fill_var.get(),
                per_page=self.per_page_var.get(),
                quiet=True,
            )
            names = "\n".join(f"  • {p.name}" for p in outputs)
            self.status.set(f"完成，共 {len(outputs)} 个文件")
            messagebox.showinfo("生成完成", f"已保存到:\n{out_dir}\n\n{names}")
        except Exception as e:
            self.status.set("生成失败")
            messagebox.showerror("错误", str(e))

    def _open_output(self) -> None:
        d = Path(self.output_dir.get())
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(d)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(d)], check=False)
        else:
            subprocess.run(["xdg-open", str(d)], check=False)


def main() -> None:
    app = LabelApp()
    app.mainloop()


if __name__ == "__main__":
    main()
