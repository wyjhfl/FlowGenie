# FlowGenie - 自然语言驱动的 AI 智能工作流生成器

TRAE AI 创造力大赛 · 学习工作赛道 · 初赛 Demo

## 项目结构

```
FlowGenie/
├── frontend/    # React + ReactFlow 前端（部署 Vercel）
├── backend/     # FastAPI + DeepSeek 后端（部署 Render）
└── .trae/documents/  # 开发计划文档
```

## 功能特性

### 工作流引擎
- 自然语言生成工作流（LLM 解析 + 模板匹配双轨）
- 就绪队列模式异步执行，支持条件分支（if_else/switch）、循环（loop）、失败策略（stop/continue/branch）
- 调试模式：单步执行、继续、中止
- 重试：从失败步骤重试（from_failed）或从头重试（from_start）
- SSE 流式执行进度推送
- 并发控制：信号量限流（5 并发），loop 子流程复用槽位

### 触发方式
- 手动触发：前端按钮一键执行
- 定时触发：cron 表达式 + 时区，调度器自动启停
- Webhook 触发：HMAC-SHA256 签名鉴权 + 令牌桶限流（30s/10次），202 异步执行

### 工具库（37 个内置工具）
- 数据获取：HTTP 请求、网页抓取、RSS 订阅、数据库查询、GitHub API
- AI 处理：摘要、分析、Review、生成、翻译、分类、信息抽取
- 数据处理：数据转换、图表生成、代码执行、文本模板、JSON 路径、正则提取、日期格式化、数组操作、数学计算
- 输出推送：邮件、Slack、微信、钉钉、Telegram、飞书、Notion、文件写入
- 逻辑控制：条件分支、循环遍历、延时等待、多路分支

### 管理功能
- 工作流 CRUD + 标签 + 批量操作 + 导入/导出（JSON）
- 版本管理：自动快照 + 回滚
- 执行历史：步骤级结果可视化、运行对比（diff）
- Dashboard：执行指标（总量/成功率/耗时/7-30-90天趋势/工具频次/失败聚类/百分位）
- 凭证管理：SMTP/IM/GitHub/数据库凭证统一管理 + 连通性测试
- 偏好设置：schema 驱动的用户偏好，执行期自动填充工具参数
- 失败通知：邮件/微信/钉钉/Slack/Telegram 多渠道告警

### 安全加固
- code_node 沙箱：白名单优先导入策略 + AST 危险属性检查 + 受限 builtins + 10s 超时
- SSRF 防护：URL 协议白名单 + DNS 解析 + 内网 IP 拒绝（http_request/web_scraper 共用）
- SQL 注入防护：注释剥离 + 白名单（SELECT/WITH）+ 黑名单 + 参数化绑定
- Webhook 鉴权：HMAC-SHA256 签名 + 令牌桶限流
- 错误脱敏：Bearer token/API key/密码/内网 IP 统一脱敏（execute/webhooks/scheduler/notify 共用）

## 本地开发

### 后端
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # 填入 LLM_API_KEY
uvicorn main:app --reload
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

### 测试
```bash
# 后端（146 用例）
cd backend && python -m pytest --tb=short -q

# 前端（38 用例）
cd frontend && npx vitest run
```

## 技术栈
- 前端：React 18 + ReactFlow + Vite + TypeScript + shadcn/ui
- 后端：FastAPI + DeepSeek（OpenAI SDK 兼容）+ SQLAlchemy + SQLite
- 部署：Vercel（前端） + Render（后端）
