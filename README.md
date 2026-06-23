# FlowGenie - 自然语言驱动的 AI 智能工作流生成器

TRAE AI 创造力大赛 · 学习工作赛道 · 初赛 Demo

## 项目结构

```
FlowGenie/
├── frontend/    # React + ReactFlow 前端（部署 Vercel）
├── backend/     # FastAPI + DeepSeek 后端（部署 Render）
└── .trae/documents/  # 开发计划文档
```

## 本地开发

### 后端
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # 填入 DEEPSEEK_API_KEY
uvicorn main:app --reload
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

## 技术栈
- 前端：React 18 + ReactFlow + Vite + TypeScript
- 后端：FastAPI + DeepSeek（OpenAI SDK 兼容）
- 部署：Vercel（前端） + Render（后端）
