# 外网使用 & 本地软件说明

## 一、本地桌面软件（推荐，最简单）

不需要浏览器、不需要联网，双击即可用。

### 直接运行

```powershell
cd d:\Users\pc\Desktop\stock_project
pip install -r requirements.txt
python desktop_app.py
```

### 打包成 exe（发给同事用）

双击 `build_exe.bat`，完成后在 `dist\FBA条码排版.exe`。

把 **exe** 复制到任意电脑即可（无需安装 Python）。  
首次运行若杀毒软件提示，选「允许」即可。

---

## 二、外网使用 — 三种方式

### 方式 A：Cloudflare 隧道（最快，适合临时给外人用）

1. 本机先启动网页：`streamlit run app.py`
2. 安装 [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
3. 新开一个终端执行：

```powershell
cloudflared tunnel --url http://localhost:8501
```

4. 终端会显示一行 `https://xxxx.trycloudflare.com`，把这个链接发给对方即可访问。  
   **注意**：你关掉电脑或关闭终端，链接就失效；不要上传机密文件到公网。

---

### 方式 B：ngrok（类似 A）

1. 注册 https://ngrok.com 并安装 ngrok  
2. `streamlit run app.py`  
3. `ngrok http 8501`  
4. 使用生成的 `https://xxx.ngrok.io` 链接

免费版链接会变化，适合临时演示。

---

### 方式 C：Streamlit Cloud（长期公网，需 GitHub）

适合长期固定网址，步骤概要：

1. 把 `stock_project` 推到 **GitHub 私有或公开仓库**  
2. 打开 https://share.streamlit.io ，用 GitHub 登录  
3. New app → 选仓库 → Main file 填 `app.py`  
4. Deploy  

之后会得到固定地址，例如 `https://your-app.streamlit.app`。  
**注意**：上传的 PDF 会经过 Streamlit 服务器，敏感业务数据请用私有部署或本地 exe。

---

### 方式 D：自己的云服务器（阿里云 / 腾讯云）

适合公司长期使用：

1. 买一台带公网 IP 的 Linux 或 Windows 服务器  
2. 安装 Python、`pip install -r requirements.txt`  
3. 用 `streamlit run app.py --server.port 8501 --server.address 0.0.0.0`  
4. 安全组放行 8501 端口，或用 Nginx 配 HTTPS 域名  

需要一定运维经验；数据在自己服务器上，比 Streamlit Cloud 更可控。

---

## 怎么选？

| 需求 | 建议 |
|------|------|
| 自己/同事电脑用，不联网 | **desktop_app.py** 或 **打包 exe** |
| 临时给外网的人用一次 | **Cloudflare 隧道** 或 **ngrok** |
| 长期固定网址、可分享 | **Streamlit Cloud** 或 **云服务器** |
| 数据不能出公司 | **只用本地 exe**，不要公网部署 |

---

## 网页版 vs 桌面版

| | 网页 `app.py` | 桌面 `desktop_app.py` |
|--|----------------|------------------------|
| 启动 | `streamlit run app.py` | `python desktop_app.py` |
| 界面 | 浏览器 | Windows 窗口 |
| 外网 | 可配合隧道/云部署 | 仅本机 |
| 打包 exe | 较难（体积大） | `build_exe.bat` 一键打包 |
