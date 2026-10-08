"""
FBA 工具站 — 网页版

功能:
  1. 条码 A4 排版 (按页码拆批; 支持无缝/留缝/经典虚线格)
  2. PDF 转曲 (文字转曲线, 避免缺字体打不开)
  3. PDF 解锁

启动:
    streamlit run app.py
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import fitz
import streamlit as st

from make_labels import check_pdf_file, detect_label_frame
from pdf_outline import outline_pdf
from pdf_unlock import is_encrypted, unlock_pdf
from run_batches import run_batches


def pdf_has_outer_frame(path: Path) -> bool:
    """首页是否有外黑框 (带框标签)。"""
    doc = fitz.open(str(path))
    try:
        if doc.page_count < 1:
            return False
        frame, _ = detect_label_frame(doc[0])
        media = doc[0].rect
        # 外框明显小于整页, 视为带框标签
        return abs(frame) < 0.98 * abs(media) and abs(frame) > 0.35 * abs(media)
    finally:
        doc.close()

st.set_page_config(
    page_title="FBA 工具站",
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


def page_layout() -> None:
    st.header("条码 A4 排版")
    st.caption(
        "上传每页 1 个标签的 PDF。"
        " **带黑框** 的文件请用「无缝贴边」或「留缝裁切」，避免塞进经典虚线格错位。"
    )

    with st.sidebar:
        st.subheader("排版选项")
        per_page = st.selectbox(
            "每页标签数",
            options=[4, 6, 9, 2],
            index=0,
            format_func=lambda n: {
                4: "4 个 (2列×2行)",
                6: "6 个 (2列×3行)",
                9: "9 个 (3列×3行)",
                2: "2 个 (2列×1行)",
            }[n],
            help="和原来一样可自选；无缝/留缝/经典三种样式都支持这些数量。",
            key="layout_per_page",
        )
        style = st.radio(
            "排版样式",
            options=["seamless", "gutter", "classic"],
            index=0,
            format_func=lambda k: {
                "seamless": "无缝贴边（推荐带框）",
                "gutter": "留缝裁切（中间留白）",
                "classic": "经典虚线格",
            }[k],
            help="带外框的 AWD/FBA 标签请选无缝或留缝；经典格适合已去框或无框文件。与「每页几个」互不影响。",
            key="layout_style",
        )
        gutter_pt = 6.0
        if style == "gutter":
            gutter_pt = st.slider(
                "空隙宽度 (pt)",
                min_value=3.0,
                max_value=12.0,
                value=6.0,
                step=1.0,
                key="layout_gutter",
            )
        align = "center"
        fill = False
        if style == "classic":
            align = st.selectbox(
                "格子内对齐", ["center", "top-left"], index=0, key="layout_align"
            )
            fill = st.checkbox("放大填满格子", value=False, key="layout_fill")
        no_grid = st.checkbox("不绘制裁切线/虚线", value=False, key="layout_nogrid")

    uploaded = st.file_uploader(
        "上传源 PDF（条码）",
        type=["pdf"],
        key="layout_upload",
        help="Illustrator 导出的标准 PDF，不要用 WPS 另存为",
    )

    if "batch_table" not in st.session_state:
        st.session_state.batch_table = [dict(r) for r in DEFAULT_BATCHES]

    total_pages: int | None = None
    if uploaded is not None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / uploaded.name
            src.write_bytes(uploaded.getvalue())
            try:
                check_pdf_file(src)
                total_pages = pdf_page_count(src)
                has_frame = pdf_has_outer_frame(src)
                st.success(f"已识别源文件：**{total_pages}** 页")
                if has_frame:
                    st.info(
                        "检测到标签**外黑框**。请使用侧边栏「无缝贴边」或「留缝裁切」，"
                        "不要用「经典虚线格」，以免错位。"
                    )
                    if style == "classic":
                        st.warning("当前选的是经典虚线格，带框文件容易错位。")
            except ValueError as e:
                st.error(str(e))
                return

    st.subheader("批次设置（页码从 1 开始）")
    col_add, col_reset, col_all, _ = st.columns([1, 1.4, 1.2, 2.4])
    with col_add:
        if st.button("＋ 添加一行", key="layout_add"):
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
        if st.button("恢复默认 (IT12/30/50)", key="layout_reset"):
            st.session_state.batch_table = [dict(r) for r in DEFAULT_BATCHES]
            st.rerun()
    with col_all:
        if st.button(
            "整文件一批",
            key="layout_all_pages",
            disabled=total_pages is None,
            help="把批次改成从第 1 页到最后一页，整本导出一个 PDF",
        ):
            stem = Path(uploaded.name).stem if uploaded is not None else "output"
            st.session_state.batch_table = [
                {
                    "启用": True,
                    "名称": stem,
                    "起始页": 1,
                    "结束页": int(total_pages),
                    "输出文件名": f"{stem}_{per_page}up.pdf",
                }
            ]
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
        key="layout_editor",
    )
    if hasattr(edited, "to_dict"):
        st.session_state.batch_table = edited.to_dict("records")
    else:
        st.session_state.batch_table = list(edited)

    generate = st.button(
        "生成排版 PDF", type="primary", disabled=uploaded is None, key="layout_go"
    )

    if generate and uploaded is not None and total_pages is not None:
        try:
            batches = batches_from_table(st.session_state.batch_table, total_pages)
        except ValueError as e:
            st.error(str(e))
            return

        compact = style == "seamless"
        gutter = float(gutter_pt) if style == "gutter" else None

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
                        per_page=per_page,
                        compact=compact,
                        gutter=gutter,
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
                    key="layout_zip",
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
                            key=f"layout_dl_{i}",
                        )


def page_outline() -> None:
    st.header("PDF 转曲")
    st.caption(
        "客户发来的稿子没转曲、缺字体打不开时："
        "上传后自动把**文字转成曲线**，再下载转曲后的 PDF。"
    )
    st.info(
        "说明：相当于 Illustrator「文字 → 创建轮廓」。"
        "转曲后文字不能再直接改字；页数很多时会稍慢，文件可能变大。"
        "请上传标准 **%PDF-** 文件（不要用 WPS 另存为的 TSD）。"
    )

    uploaded = st.file_uploader(
        "上传客户原稿 PDF",
        type=["pdf"],
        key="outline_upload",
    )

    if uploaded is not None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / uploaded.name
            src.write_bytes(uploaded.getvalue())
            try:
                check_pdf_file(src)
                n = pdf_page_count(src)
                st.success(f"已识别：**{n}** 页 · {uploaded.name}")
            except ValueError as e:
                st.error(str(e))
                return

    go = st.button(
        "开始转曲", type="primary", disabled=uploaded is None, key="outline_go"
    )

    if go and uploaded is not None:
        with st.spinner("正在转曲，请稍候…"):
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                src = work / uploaded.name
                src.write_bytes(uploaded.getvalue())
                stem = Path(uploaded.name).stem
                out = work / f"{stem}_outlined.pdf"
                try:
                    outline_pdf(src, out)
                except Exception as e:
                    st.error(f"转曲失败: {e}")
                    return

                data = out.read_bytes()
                st.success(
                    f"转曲完成 · 输出约 **{len(data) / 1024:.0f} KB**"
                )
                st.download_button(
                    "下载转曲后的 PDF",
                    data=data,
                    file_name=f"{stem}_outlined.pdf",
                    mime="application/pdf",
                    type="primary",
                    key="outline_dl",
                )


def page_unlock() -> None:
    st.header("PDF 解锁")
    st.caption(
        "客户发来的加密 PDF：输入打开密码后，导出一份**无密码**的副本，方便本机打开和继续排版。"
    )
    st.info(
        "需要客户提供的正确密码才能解锁。"
        "本工具不会破解未知密码。"
        "请上传标准 **%PDF-** 文件。"
    )

    uploaded = st.file_uploader(
        "上传加密 PDF",
        type=["pdf"],
        key="unlock_upload",
    )
    password = st.text_input(
        "打开密码",
        type="password",
        value="",
        key="unlock_password",
        help="若客户说没有密码仍打不开，可先留空试一次",
        placeholder="输入密码（可留空）",
    )

    enc_hint = None
    if uploaded is not None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / uploaded.name
            src.write_bytes(uploaded.getvalue())
            try:
                with open(src, "rb") as f:
                    header = f.read(8)
                if header.startswith(b"%TSD-"):
                    st.error("这是 WPS 私有格式 (TSD)，不是标准 PDF。")
                    return
                if not header.startswith(b"%PDF-"):
                    st.error("不是有效 PDF 文件。")
                    return
                enc = is_encrypted(src)
                enc_hint = enc
                if enc:
                    st.warning(f"**{uploaded.name}** 已加密，请填写密码后解锁。")
                else:
                    st.success(
                        f"**{uploaded.name}** 看起来未加密。"
                        "仍可点下方按钮另存一份无限制副本。"
                    )
            except Exception as e:
                st.error(str(e))
                return

    go = st.button(
        "解锁并下载",
        type="primary",
        disabled=uploaded is None,
        key="unlock_go",
    )

    if go and uploaded is not None:
        with st.spinner("正在解锁…"):
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                src = work / uploaded.name
                src.write_bytes(uploaded.getvalue())
                stem = Path(uploaded.name).stem
                out = work / f"{stem}_unlocked.pdf"
                try:
                    unlock_pdf(src, out, password=password or "")
                except ValueError as e:
                    st.error(str(e))
                    return
                except Exception as e:
                    st.error(f"解锁失败: {e}")
                    return

                data = out.read_bytes()
                st.success(
                    f"解锁成功 · 输出约 **{len(data) / 1024:.0f} KB**"
                    + ("（原文件未加密）" if enc_hint is False else "")
                )
                st.download_button(
                    "下载解锁后的 PDF",
                    data=data,
                    file_name=f"{stem}_unlocked.pdf",
                    mime="application/pdf",
                    type="primary",
                    key="unlock_dl",
                )


def main() -> None:
    st.title("FBA 工具站")
    tab1, tab2, tab3 = st.tabs(
        ["📦 条码 A4 排版", "✏️ PDF 转曲", "🔓 PDF 解锁"]
    )
    with tab1:
        page_layout()
    with tab2:
        page_outline()
    with tab3:
        page_unlock()

    with st.sidebar:
        st.divider()
        st.markdown(
            "**通用注意**\n\n"
            "- 上传 **%PDF-** 标准文件\n"
            "- 不要用 WPS 另存为（会变成 TSD）\n"
            "- Illustrator：**文件 → 存储为 → Adobe PDF**"
        )


if __name__ == "__main__":
    main()
