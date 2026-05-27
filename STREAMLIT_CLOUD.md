# 部署到 Streamlit Cloud（一步步）

部署后你会得到一个固定网址，例如：`https://你的应用名.streamlit.app`

---

## 部署前须知

1. **应用是公开的**：免费版 Streamlit Cloud 上，知道链接的人都能打开（不能设密码）。条码 PDF 会在云端临时处理，**不要用公开仓库 + 公开 App 处理绝密数据**。若需私密，用本地 `desktop_app.py` 或自建服务器。
2. **不要上传 PDF 到 GitHub**：`.gitignore` 已忽略 `*.pdf`，只上传代码。
3. **源文件必须是标准 PDF**（`%PDF-`），不能是 WPS 的 TSD 格式。

---

## 第一步：安装 Git（若还没有）

下载：https://git-scm.com/download/win  
安装后打开 PowerShell，执行 `git --version` 确认可用。

---

## 第二步：把代码推到 GitHub

在 PowerShell 中执行（路径按你的实际目录改）：

```powershell
cd d:\Users\pc\Desktop\stock_project

git init
git add .
git status
```

确认 **没有** `11_ai.pdf` 等 PDF 被加入（应在 .gitignore 里）。

```powershell
git commit -m "FBA label layout app for Streamlit Cloud"

git branch -M main
```

在浏览器打开 https://github.com/new 创建新仓库，例如名：`fba-label-layout`，**不要**勾选 “Add a README”（仓库要空的）。

然后（把 `你的用户名` 换成你的 GitHub 用户名）：

```powershell
git remote add origin https://github.com/你的用户名/fba-label-layout.git
git push -u origin main
```

若提示登录，用 GitHub 账号或 [Personal Access Token](https://github.com/settings/tokens) 作为密码。

---

## 第三步：在 Streamlit Cloud 部署

1. 打开 **https://share.streamlit.io**
2. 用 **GitHub** 登录
3. 点击 **New app**
4. 填写：
   - **Repository**：`你的用户名/fba-label-layout`
   - **Branch**：`main`
   - **Main file path**：`app.py`
5. 点击 **Deploy**

等待 2～5 分钟，出现 “Your app is live” 和网址。

---

## 第四步：使用线上版

1. 打开你的 `https://xxx.streamlit.app`
2. 上传 Illustrator 导出的 PDF
3. 在表格里改页码范围（默认 IT12 / IT30 / IT50）
4. 点 **生成 PDF** → 下载 ZIP 或单个文件

---

## 以后更新代码

改完本地代码后：

```powershell
cd d:\Users\pc\Desktop\stock_project
git add .
git commit -m "更新说明"
git push
```

Streamlit Cloud 会自动重新部署（约 1～3 分钟）。

---

## 常见问题

### 部署失败 / ModuleNotFoundError

确认仓库根目录有 `requirements.txt`，且包含：

```
pypdf>=4.0.0
reportlab>=4.0.0
pymupdf>=1.23.0
streamlit>=1.30.0
```

在 Cloud 日志里看具体缺哪个包。

### 上传 PDF 失败

免费版单文件上传约 **200MB**（已在 `.streamlit/config.toml` 配置）。178 页标签 PDF 一般远小于此。

### 生成很慢或超时

标签很多时（如 178 个）处理要几十秒。若超时，可分批生成（例如先 1–90，再 91–178），或升级 Streamlit 付费方案。

### 想改应用网址名称

在 share.streamlit.io → 你的 App → **Settings** → 可改 subdomain（若未被占用）。

---

## 仓库里应包含的文件

| 文件 | 必需 |
|------|------|
| `app.py` | 是（入口） |
| `make_labels.py` | 是 |
| `run_batches.py` | 是 |
| `requirements.txt` | 是 |
| `.streamlit/config.toml` | 建议 |
| `11_ai.pdf` | **否**（用户在线上传） |

可选：`batches.json`、`README.md`、本说明文件。
