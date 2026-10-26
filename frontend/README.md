# KnowPath 前端

前端是单一的原生 JS 单页应用（无框架依赖），由 Vite 提供开发服务器、`/api` 代理与构建产物。页面骨架在 `index.html`，交互逻辑拆成三个经典脚本：`src/app.js`（主工作区）、`src/workspace.js`（对象工作区增强）、`src/learning-shell.js`（学习路径侧栏增强），样式在 `src/styles.css`。

认证使用 RuoYi-FastAPI 的 JWT：登录后把 token 存入 `localStorage['knowpath:token']`，请求时附带 `Authorization: Bearer <token>`。

## 开发

先启动 RuoYi-FastAPI 后端（9099）：

```powershell
cd knowpath-ruoyi/ruoyi-fastapi-backend
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe app.py
```

另开终端启动前端开发服务器：

```powershell
cd knowpath/frontend
npm install
npm run dev
```

访问 http://127.0.0.1:5180/。Vite 会把 `/api/`、`/health/` 和 `/media/` 代理到 RuoYi 后端（默认 `http://127.0.0.1:9099`，可用 `VITE_API_TARGET` 覆盖）。

## 构建

```powershell
npm run build
```

构建产物位于 `frontend/dist/`，Docker Compose 会自动构建并由 Nginx 托管。
