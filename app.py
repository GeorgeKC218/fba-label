"""
FBA 条码 A4 排版 — 网页版

启动:
    pip install -r requirements.txt
    streamlit run app.py

浏览器会自动打开; 上传 Illustrator 导出的标准 PDF, 填写页码范围, 生成并下载。
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import fitz
import streamlit as st

from make_labels import check_pdf_file
from run_batches import run_batches

st.set_page_config(
    page_title="FBA 条码 A4 排版",
    page_icon="📦",
    layout="wide",
)

DEFAULT_BATCHES = [
    {
        "启用": True,
        "名称": "GC-259_It12",
        "起始页": 1,
        "结束页": 90,
        "输出文件名": "GC-259_It12.pdf",
    },
    {
        "启用": True,
        "名称": "GC-230_It30",
        "起始页": 91,
        "结束页": 107,
        "输出文件名": "GC-230_It30.pdf",
    },
    {
        "启用": True,
        "名称": "GC-258_It50",
        "起始页": 108,
        "结束页": 178,
        "输出文件名": "GC-258_It50.pdf",
    },
]


def pdf_page_count(path: Path) -> int:
    doc = fitz.open(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def batches_from_table(rows: list[dict], total_pages: int) -> list[dict]:
    batches: list[dict] = []
    used: list[tuple[int, int]] = []

    for row in rows:
        if not row.get("启用", True):
            continue
        name = str(row.get("名称", "batch")).strip() or "batch"
        start = int(row["起始页"])
        end = int(row["结束页"])
        out_name = str(row.get("输出文件名", f"{name}.pdf")).strip()
        if not out_name.lower().endswith(".pdf"):
            out_name += ".pdf"

        if start < 1 or end < start:
            raise ValueError(f"「{name}」页码无效: {start}-{end}")
        if end > total_pages:
            raise ValueError(
                f"「{name}」结束页 {end} 超过源文件总页数 {total_pages}"
            )
        for s0, e0 in used:
            if not (end < s0 or start > e0):
                raise ValueError(f"「{name}」与第 {s0}-{e0} 页范围重叠")
        used.append((start, end))

        batches.append(
            {
                "name": name,
                "start": start,
                "count": end - start + 1,
                "output": out_name,
            }
        )

    if not batches:
        raise ValueError("请至少启用一个批次")
    return batches


def make_zip(files: list[Path]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, arcname=p.name)
    return buf.getvalue()


def main() -> None:
    st.title("FBA 条码 A4 排版")
    st.caption(
        "上传 Illustrator 导出的标准 PDF（每页 1 个标签），"
        "按页码分成多份 A4 排版文件（每页 6 个，带虚线格）。"
    )
    with st.expander("使用说明", expanded=False):
        st.markdown(
            """
1. 上传 **%PDF-** 标准文件（Illustrator 导出，不要用 WPS 另存为）
2. 在下方表格填写每批 **起始页 / 结束页**（从 1 开始）
3. 点击 **生成 PDF**，下载 ZIP 或单个文件
4. 默认三批：IT12 (1–90)、IT30 (91–107)、IT50 (108–178)，可按需修改
            """
        )

    with st.sidebar:
        st.header("选项")
        align = st.selectbox("格子内对齐", ["center", "top-left"], index=0)
        fill = st.checkbox("放大填满格子", value=False, help="默认 1:1 不放大")
        no_grid = st.checkbox("不绘制虚线", value=False)
        st.divider()
        st.markdown(
            "**注意**\n\n"
            "- 请上传 **%PDF-** 标准文件\n"
            "- 不要用 WPS 另存为（会变成 TSD 格式）\n"
            "- 用 Illustrator：**文件 → 存储为 → Adobe PDF**"
        )

    uploaded = st.file_uploader(
        "上传源 PDF",
        type=["pdf"],
        help="例如 FBA19F1W4F8T-1779858349247.pdf（178 页）",
    )

    if "batch_table" not in st.session_state:
        st.session_state.batch_table = DEFAULT_BATCHES.copy()

    st.subheader("批次设置（页码从 1 开始）")
    col_add, col_reset, _ = st.columns([1, 1, 4])
    with col_add:
        if st.button("＋ 添加一行"):
            st.session_state.batch_table.append(
                {
                    "启用": True,
                    "名称": f"批次{len(st.session_state.batch_table) + 1}",
                    "起始页": 1,
                    "结束页": 1,
                    "输出文件名": "output.pdf",
                }
            )
            st.rerun()
    with col_reset:
        if st.button("恢复默认 (IT12/30/50)"):
            st.session_state.batch_table = DEFAULT_BATCHES.copy()
            st.rerun()

    edited = st.data_editor(
        st.session_state.batch_table,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "启用": st.column_config.CheckboxColumn("启用", default=True),
            "名称": st.column_config.TextColumn("名称", required=True),
            "起始页": st.column_config.NumberColumn("起始页", min_value=1, step=1),
            "结束页": st.column_config.NumberColumn("结束页", min_value=1, step=1),
            "输出文件名": st.column_config.TextColumn("输出文件名", required=True),
        },
        hide_index=True,
    )
    if hasattr(edited, "to_dict"):
        st.session_state.batch_table = edited.to_dict("records")
    else:
        st.session_state.batch_table = list(edited)

    total_pages: int | None = None
    if uploaded is not None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / uploaded.name
            src.write_bytes(uploaded.getvalue())
            try:
                check_pdf_file(src)
                total_pages = pdf_page_count(src)
                st.success(f"已识别源文件：**{total_pages}** 页")
            except ValueError as e:
                st.error(str(e))
                return

    generate = st.button("生成 PDF", type="primary", disabled=uploaded is None)

    if generate and uploaded is not None and total_pages is not None:
        try:
            batches = batches_from_table(st.session_state.batch_table, total_pages)
        except ValueError as e:
            st.error(str(e))
            return

        with st.spinner(f"正在生成 {len(batches)} 个文件…"):
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                src = work / uploaded.name
                src.write_bytes(uploaded.getvalue())
                out_dir = work / "out"
                out_dir.mkdir()

                try:
                    outputs = run_batches(
                        src,
                        batches,
                        output_dir=out_dir,
                        align=align,
                        fill=fill,
                        no_grid=no_grid,
                        quiet=True,
                    )
                except Exception as e:
                    st.error(f"生成失败: {e}")
                    return

                st.success(f"已生成 **{len(outputs)}** 个文件")

                zip_bytes = make_zip(outputs)
                st.download_button(
                    "下载全部 (ZIP)",
                    data=zip_bytes,
                    file_name="fba_labels.zip",
                    mime="application/zip",
                    type="primary",
                )

                st.divider()
                st.subheader("单独下载")
                cols = st.columns(min(len(outputs), 3))
                for i, p in enumerate(outputs):
                    with cols[i % len(cols)]:
                        st.download_button(
                            label=p.name,
                            data=p.read_bytes(),
                            file_name=p.name,
                            mime="application/pdf",
                            use_container_width=True,
                        )


if __name__ == "__main__":
    main()
