# 条码标签 A4 排版工具

把 **11_ai.pdf**（每页 1 个标签，如 178 页）按顺序排到 **A4** 上，每页 6 个（2 列 × 3 行），虚线网格与 **12_ai.pdf**（Illustrator 导出）一致。

```
1  2
3  4
5  6
```

## 安装

```bash
pip install -r requirements.txt
```

## 使用

### 单文件

```bash
python make_labels.py 11_ai.pdf 178 -o output_178.pdf
```

### 分成 3 个 PDF (IT12 / IT30 / IT50)

编辑 `batches.json` 后一键生成:

```bash
python run_batches.py
```

| 输出文件 | 源页 (1-based) | 数量 |
|----------|----------------|------|
| GC-259_It12.pdf | 1–90 | 90 |
| GC-230_It30.pdf | 91–107 | 17 |
| GC-258_It50.pdf | 108–178 | 71 |

不写 json、命令行直接指定:

```bash
python run_batches.py --input 11_ai.pdf --batch "IT12:1-90,IT30:91-107,IT50:108-178"
```

以后换批次: 改 `batches.json` 里的 `start`、`count`、`output` 即可。

## 网页版（上传 + 填页码）

```bash
pip install -r requirements.txt
streamlit run app.py
```

浏览器会打开本地页面:

1. 上传 Illustrator 导出的标准 PDF
2. 在表格里填写每批的**起始页 / 结束页** 和输出文件名（默认 IT12/30/50）
3. 点击 **生成 PDF**，下载 ZIP 或单个文件

同一局域网内其他人可访问终端里显示的 `Network URL`（可选）。

## 本地桌面软件（无需浏览器）

```bash
python desktop_app.py
```

或双击 `start_desktop.bat`。打包 exe：双击 `build_exe.bat` → `dist\FBA条码排版.exe`。

## 部署到 Streamlit Cloud（固定网址）

按 **[STREAMLIT_CLOUD.md](STREAMLIT_CLOUD.md)** 操作：代码推 GitHub → https://share.streamlit.io 部署 → `app.py` 作为入口。

其他外网方式见 [DEPLOY.md](DEPLOY.md)。

## 网格参数 (来自 12_ai.pdf)

| 参数 | 值 |
|------|-----|
| 纸张 | A4 210×297 mm |
| 格子 | 297.64 × 240 pt (约 105×84.7 mm) |
| 下边距 | 61.61 pt |
| 上边距 | 60.22 pt |
| 虚线 | 11.761 / 11.915 pt |
| 线宽 | 0.5 pt |

## 检查 PDF

```bash
python inspect_ref.py 12_ai.pdf
python inspect_ref.py 11_ai.pdf
```

文件必须是标准 PDF（文件头 `%PDF-`），不能是 WPS 的 `%TSD-` 格式。请用 Illustrator **文件 → 存储为 → Adobe PDF** 导出。
