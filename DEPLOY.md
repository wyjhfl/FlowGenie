# 部署指南

## 前置条件
- GitHub 账号（用于推送代码）
- DeepSeek API Key（从 https://platform.deepseek.com 获取）
- Vercel 账号（https://vercel.com）
- Render 账号（https://render.com）

## 步骤 1：推送代码到 GitHub

```bash
# 在项目根目录初始化 git
git init
git add .
git commit -m "FlowGenie 初赛 Demo"

# 在 GitHub 创建仓库后
git remote add origin https://github.com/你的用户名/FlowGenie.git
git branch -M main
git push -u origin main
```

## 步骤 2：部署后端到 Render

1. 登录 https://dashboard.render.com
2. 点击 "New +" → "Web Service"
3. 连接 GitHub 仓库
4. 配置：
   - **Name**: flowgenie-backend
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
5. 环境变量：
   - `DEEPSEEK_API_KEY` = 你的 DeepSeek API Key
   - `FRONTEND_URL` = （先留空，部署完前端后填 Vercel 地址）
6. 点击 "Create Web Service"
7. 部署完成后记下后端地址，如 `https://flowgenie-backend.onrender.com`

## 步骤 3：部署前端到 Vercel

1. 登录 https://vercel.com
2. 点击 "Add New" → "Project"
3. 导入 GitHub 仓库
4. 配置：
   - **Root Directory**: `frontend`
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
5. 环境变量：
   - `VITE_API_BASE_URL` = `https://flowgenie-backend.onrender.com`（替换为 Render 后端地址）
6. 点击 "Deploy"
7. 部署完成后记下前端地址，如 `https://flowgenie.vercel.app`

## 步骤 4：更新后端 CORS 白名单

回到 Render 后端服务，更新环境变量：
- `FRONTEND_URL` = `https://flowgenie.vercel.app`（替换为 Vercel 前端地址）

Render 会自动重新部署。

## 步骤 5：验证

访问前端地址，测试：
1. 点击场景模板按钮，确认能生成可视化工作流
2. 自由输入需求，确认能生成工作流（需配置 DeepSeek API Key）
3. 点击导出，确认能生成 TRAE Skill 文件

## 注意事项

- Render 免费层服务会在 15 分钟无请求后休眠，首次访问可能需要等待 30-60 秒冷启动
- DeepSeek API 需要充值才能使用，新用户有少量免费额度
- 如果没有 DeepSeek API Key，后端会走 Mock 响应，3 个场景模板仍可正常演示
