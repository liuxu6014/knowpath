# KnowPath

个性化学习系统（KnowPath），从 Django 迁移到 RuoYi-FastAPI（Python）架构。

## 目录结构

- `backend/` — 后端：RuoYi-FastAPI v2.0.0（FastAPI + SQLAlchemy 2.0 async + MySQL + Redis + JWT），默认端口 **9099**
- `frontend/` — 前端：Vue 3 + Element Plus（RuoYi-Vue3 风格），Vite 开发端口 **5180**，代理 `/api` → 9099

## 运行

### 后端

```bash
cd backend
pip install -r requirements.txt
# 先准备 .env.dev（含数据库等配置，不提交到仓库）
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python app.py
```

### 前端

```bash
cd frontend
npm install
npm run dev   # http://localhost:5180
```

## 默认账号

用户名：`admin`，密码：`admin123`（RuoYi 框架默认账号，首次登录后请修改）。
