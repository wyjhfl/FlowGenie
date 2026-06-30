# FlowGenie 初赛 Demo 发帖内容

> 以下为初赛专区发帖内容,按官方模板 4 部分编写。部署完成后补充体验地址和截图。

---

**【标签】** 学习工作

**【标题】** 【学习工作赛道】FlowGenie - 自然语言驱动的 AI 智能工作流生成器

---

## 1. Demo 简介

**是什么:** FlowGenie 是一个 Web 应用,用户通过自然语言描述需求,AI 自动拆解任务、匹配工具、生成可视化工作流,并支持一键执行、调试和导出。它不仅是一个"工作流生成器",更是一个**端到端可运行的工作流自动化平台**——生成即可执行,执行即可监控,监控即可优化。

**面向谁:** 数据分析师、内容运营、开发者、产品经理等需要自动化工作流但不懂节点配置的非技术用户,以及希望快速搭建自动化原型的开发者。

**主要功能:**

### 💬 自然语言驱动的工作流生成
- 用一句话描述需求,如"每天早上8点抓取科技新闻生成摘要推送到微信"
- AI 自动识别场景、拆解步骤、匹配工具(内置 20+ 工具库,覆盖触发/数据获取/AI处理/数据处理/输出推送 5 大类)
- 支持多轮对话迭代调整工作流(如"把第2步改成调用 Claude 分析")

### 🔄 端到端工作流执行引擎
- **实时流式执行**:WebSocket + SSE 推送步骤进度,边执行边看结果
- **人工审批节点**:关键步骤暂停等待人工批准/拒绝,支持审批评论
- **子流程嵌套**:工作流可调用其他工作流作为子流程(深度上限 5 层,循环引用检测)
- **链式触发**:工作流完成后自动触发关联工作流(支持 success/failed/always 条件,深度上限 3 层)
- **失败处理**:支持 stop/continue 两种策略,失败步骤仅跳过直接后续
- **并发控制**:信号量限制最大 5 个并发执行,防止资源耗尽

### 📊 可视化与监控
- ReactFlow 拖拽式节点画布,自定义节点按工具类型着色,支持边条件标签
- **Dashboard 执行统计**:总运行数/成功率/平均耗时/7天趋势/工具使用频率/工作流排名/失败聚类/LLM token 用量
- **执行历史**:结构化步骤结果(状态徽标/耗时/输出摘要/可展开错误详情),彩色日志级别
- **执行对比**:两次执行的步骤级 diff,定位性能/成功率变化
- **重试机制**:支持从失败步骤继续或从头重新执行

### 🔔 多触发方式
- **手动触发**:前端一键运行
- **定时调度**:Cron 表达式,APScheduler 后台执行,支持暂停/恢复/立即触发
- **Webhook 触发**:生成专属 webhook URL,支持 HMAC 签名验证,外部系统直接调用
- **链式触发**:工作流间自动联动

### 🛠️ 工具与凭证管理
- 20+ 内置工具:http_request / web_scraper / llm_summary / llm_analysis / llm_review / llm_generate / database_query / github_api / notion_api / feishu_api / send_email / send_wechat / send_slack / send_dingtalk / send_telegram / code_execute / python_export 等
- 凭证面板统一管理 SMTP/Slack/GitHub/Notion 等凭证,脱敏存储,在线测试连通性
- 用户偏好 schema 驱动渲染,工具按 applicable_tools 自动关联凭证

### 📤 多格式导出
- TRAE Skill (JSON / YAML)
- 通用 JSON 工作流定义
- **独立 Python 脚本**:导出为可执行 .py 文件,包含工具函数 + 拓扑执行 + 变量插值 + AST 安全检查

### 🎨 UI/UX
- 暗色/亮色双主题(四级灰阶层次设计)
- shadcn/ui + Radix 组件体系
- 响应式三栏布局(输入区 + 画布 + 节点详情)
- 工作流卡片支持内联重命名/标签/搜索筛选/复制/批量操作
- 命令面板(Cmd+K)快速导航

**核心流程:** 说需求 → AI 拆解 → 匹配工具 → 生成工作流 → 一键执行/调度/Webhook → 实时监控 → Dashboard 分析 → 导出复用

**界面截图:**
(部署后补充:主界面截图、工作流生成截图、执行流式监控截图、Dashboard 统计截图、导出面板截图)

## 2. Demo 创作思路

**灵感来源:** 在日常工作中,经常想"能不能让 AI 每天帮我抓取新闻并生成摘要?"但打开 Dify、n8n 等工作流工具后,面对密密麻麻的节点和复杂配置往往望而却步。我们意识到,真正的瓶颈不是 AI 能力不足,而是工作流搭建的门槛太高。

**想解决的问题:** 当前 AI 工作流工具(Dify、n8n、Coze 等)虽然功能强大,但用户必须先理解节点、连线、变量等概念才能搭建,这对占职场 80% 的非技术用户来说门槛过高。搭建一个简单工作流需要 30 分钟到数小时。而且即使搭好,执行监控、失败重试、调度触发等"运维"能力依然薄弱。

**为什么做这个方向:** 如果用户只需要像和同事说话一样描述需求,AI 就能自动完成剩下的所有工作——从生成到执行到监控到优化——那将彻底改变职场人的工作方式。FlowGenie 瞄准的是尚未被充分开发的非技术用户市场,且不止于"生成",而是覆盖工作流全生命周期。

**技术取舍:**
- 前后端分离架构(React + ReactFlow + FastAPI),Vercel(前端) + Render(后端)部署,自有域名 hfl.asia
- 内置场景模板保证 Demo 演示稳定,自由输入走真实 LLM 拆解展示 AI 能力
- 工具库插件化架构,便于后续扩展 MCP/Skill/API 接入
- SQLite 持久化(工作流/执行历史/凭证/版本),生产可平滑迁移 PostgreSQL
- WebSocket + SSE 双通道实时推送,平衡即时性与可靠性
- AST 安全检查 + 沙箱执行 + 超时保护,确保代码节点安全

## 3. Demo 体验地址

**在线体验:** https://flowgenie.hfl.asia (部署后生效)

**体验方式:**
1. 点击左侧"场景模板"按钮(新闻摘要/销售报表/Code Review 等),一键生成工作流
2. 或在输入框自由描述需求,AI 自动拆解(如"每天早上8点抓取科技新闻生成摘要推送到微信")
3. 查看中间画布的可视化工作流,点击节点查看/编辑参数
4. 点击"运行"按钮,实时查看流式执行进度和每步输出
5. 切换到"执行历史"查看过往运行详情、日志、对比两次执行 diff
6. 切换到"Dashboard"查看执行统计、工具使用频率、成功率趋势
7. 在"工作流管理"中启用定时调度或复制 Webhook URL 接入外部系统
8. 在"导出"面板选择格式(TRAE Skill / JSON / Python 脚本),生成并下载

**示例需求:**
- "每天早上8点抓取科技新闻生成摘要推送到微信"
- "每周一从数据库导出销售数据生成可视化报表邮件发给团队"
- "每次代码提交后自动进行 code review 把问题发到 slack"
- "监控某网页价格变化,降到阈值时推送 Telegram 通知"(链式触发示例)

## 4. TRAE 实践过程

**开发工具:** TRAE(全程使用 TRAE AI 完成开发,包括需求拆解、架构设计、代码生成、调试修复、测试编写、性能优化、UI 打磨)

**开发流程:**

### 4.1 创意调研与规划
- 用 TRAE 调研初赛参赛要求和评审标准
- 生成完整开发计划,明确 6 个阶段:项目骨架 → 后端核心 → 前端界面 → 联调 → 部署 → 参赛材料
- 基于"自然语言→工作流"核心创意,迭代扩展到执行引擎/监控/多触发方式等完整能力

### 4.2 项目骨架搭建
- 用 TRAE 创建 Monorepo 结构(frontend + backend)
- 前端:Vite + React + TypeScript + ReactFlow + shadcn/ui + Tailwind
- 后端:FastAPI + DeepSeek(OpenAI SDK 兼容)+ SQLite + APScheduler

### 4.3 后端核心逻辑
- 封装 LLM 调用(OpenAI SDK 兼容,支持多模型切换)
- 设计需求拆解 Prompt(系统提示词 + 工具库描述 + 场景模板匹配)
- 内置 20+ 工具库,覆盖触发/数据获取/AI处理/数据处理/输出推送 5 大类
- 实现工作流执行引擎:拓扑排序 + 并发控制 + 失败处理 + 变量插值 + 子流程 + 链式触发
- 实现 3 种触发方式:手动 / 定时调度(APScheduler)/ Webhook(HMAC 验签)
- 实现凭证管理:脱敏存储 + 在线测试 + schema 驱动
- 实现 Dashboard 统计:成功率/趋势/工具频率/失败聚类/token 用量

### 4.4 前端核心界面
- 三栏布局:左侧输入区 + 中间可视化画布 + 右侧节点详情
- ReactFlow 自定义节点组件,按工具类型着色,支持边条件标签
- shadcn/ui + Radix 组件体系,暗色/亮色双主题
- 流式执行面板:WebSocket 实时推送步骤进度 + SSE 完成事件
- Dashboard 统计面板:recharts 图表 + 工具频率 + 工作流排名
- 执行历史面板:结构化步骤结果 + 彩色日志 + 执行对比 diff
- 工作流管理:卡片视图 + 内联重命名 + 标签筛选 + 批量操作 + 版本历史

### 4.5 高级功能迭代(A 阶段:工作流执行增强)
- **A1 人工审批节点**:关键步骤暂停等待人工批准/拒绝,支持审批评论和超时处理
- **A2 子流程嵌套**:subworkflow 节点递归调用其他工作流,循环引用检测 + 深度上限 + token 聚合
- **A3 链式触发**:工作流完成后按 on_complete_trigger 配置自动触发关联工作流,支持 success/failed/always 条件
- **A4 WebSocket 基础设施**:实时双向通信,支持流式执行推送

### 4.6 质量保障
- 后端 pytest:485+ 测试用例全绿(执行引擎/工具/API/调度器/webhook/链式触发/审批/子流程全覆盖)
- 前端 vitest:104+ 测试用例全绿(组件/交互/异步时序全覆盖)
- 前端 build:生产构建通过,代码分包优化
- 全量回归:每次功能迭代后运行完整测试套件确保无回归

### 4.7 UI/UX 打磨
- 暗色模式 token bug 修复(`--border`/`--input` alpha 通道导致"全是黑"问题)
- 四级灰阶层次设计(6%/11%/15%/20%)
- 首屏 FOUC 消除(index.html 内联脚本预设主题)
- 遮罩/硬编码颜色主题适配
- shadcn/ui 组件体系规范化

### 4.8 联调与部署
- 前后端联调,所有功能跑通
- 生产构建验证通过
- 部署到 Vercel(前端)+ Render(后端),绑定自有域名 hfl.asia
- 环境变量配置:LLM API Key / CORS 白名单 / 安全 Token / 性能调优参数

**关键步骤截图:**
(部署后补充,不少于 3 张)
1. TRAE 中项目架构设计与对话截图
2. 工作流执行引擎实现的关键对话(拓扑排序/并发控制/子流程)
3. 链式触发功能实现的关键对话(深度限制/状态匹配/异步触发)
4. 暗色模式 bug 调试过程(定位 `--border` alpha 通道根因)
5. 可视化工作流界面运行截图
6. Dashboard 执行统计截图
7. 导出 TRAE Skill / Python 脚本功能截图

**关键任务 Session ID:**
(开发过程中双击 TRAE 对话复制,不少于 3 个)
- Session ID 1: (补充——项目初始化与架构设计)
- Session ID 2: (补充——工作流执行引擎实现)
- Session ID 3: (补充——链式触发 + 子流程嵌套实现)
- Session ID 4: (补充——暗色模式 bug 修复 + UI 优化)
- Session ID 5: (补充——部署配置与参赛材料)

**报名帖链接:** https://forum.trae.cn/t/topic/38651

---

## 部署步骤(Vercel + Render + hfl.asia)

### 后端 Render 部署
1. 注册 Render 账号,连接 GitHub 仓库
2. New → Web Service → 选择 FlowGenie 仓库
3. 配置:
   - Name: flowgenie-backend
   - Runtime: Python 3
   - Build Command: `pip install -r backend/requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`(工作目录 backend)
   - Plan: Free
4. 环境变量(在 Render 控制台 Environment 配置):
   - `LLM_API_KEY` = (你的 DeepSeek/APIHub key,必填)
   - `LLM_BASE_URL` = https://apihub.agnes-ai.com/v1
   - `LLM_MODEL` = agnes-2.0-flash
   - `LLM_AVAILABLE_MODELS` = agnes-2.0-flash,agnes-2.0-pro,gpt-4o,claude-3-5-sonnet
   - `FRONTEND_URL` = https://flowgenie.hfl.asia
   - `TOOL_TIMEOUT` = 120
   - `WORKFLOW_MAX_CONCURRENT` = 5
   - `LOG_FORMAT_JSON` = 1
   - **初赛 Demo 建议:`FLOWGENIE_API_KEY` 和 `FLOWGENIE_ADMIN_TOKEN` 留空**(后端放行所有请求,前端无需配认证头,简化部署)。复赛再配置认证 + 前端 API Key 输入 UI。
5. 部署后获得后端地址,如 https://flowgenie-backend.onrender.com

### 前端 Vercel 部署
1. 注册 Vercel 账号,连接 GitHub 仓库
2. New Project → 选择 FlowGenie 仓库
3. 配置:
   - Framework Preset: Vite
   - Root Directory: frontend
   - Build Command: npm run build
   - Output Directory: dist
4. 环境变量(在 Vercel 项目 Settings → Environment Variables 配置):
   - `VITE_API_BASE_URL` = https://flowgenie-backend.onrender.com (替换为 Render 实际地址)
5. 部署后获得前端地址,如 https://flowgenie.vercel.app

### 域名绑定 hfl.asia
1. 在域名 DNS 管理(阿里云/腾讯云/Cloudflare 等)添加解析:
   - 类型: CNAME
   - 主机记录: flowgenie
   - 记录值: cname.vercel-dns.com(或 Vercel 分配的地址)
2. 在 Vercel 项目 Settings → Domains 添加 `flowgenie.hfl.asia`
3. Vercel 自动签发 SSL 证书,等待 DNS 生效(通常几分钟到几小时)
4. 访问 https://flowgenie.hfl.asia 验证

### 验证清单
- [ ] 后端 Render 健康检查通过:https://flowgenie-backend.onrender.com/api/health 返回 200
- [ ] 前端 Vercel 可访问:https://flowgenie.vercel.app 加载正常
- [ ] 自有域名生效:https://flowgenie.hfl.asia 可访问且 SSL 有效
- [ ] CORS 配置正确:前端调用后端 API 无跨域错误
- [ ] LLM 调用正常:输入需求能生成工作流
- [ ] 工作流执行正常:点击运行能流式推送进度
- [ ] 定时调度正常:APScheduler 后台运行(注意 Render Free 可能休眠,需外部 ping)

---

## 开发心得

1. **场景模板 + LLM 双轨设计**:为了保证 Demo 演示稳定,典型场景走预定义模板,自由输入走真实 LLM 拆解。这样即使 LLM 响应慢或异常,核心演示也不受影响。

2. **工具库插件化架构**:工具定义为标准化结构(name/display_name/category/params_schema),便于后续扩展 MCP/Skill/API 接入,也为复赛的工作流市场打下基础。

3. **执行引擎的工程权衡**:
   - 拓扑排序 + 并发信号量(最大 5 并发)平衡执行效率与资源保护
   - 失败步骤仅跳过直接后续(而非全部),最大化工作流完成度
   - 子流程复用父流程并发槽位(`_acquire_lock=False`),避免死锁
   - 链式触发用 `loop.create_task` 异步触发,不阻塞当前请求

4. **测试驱动开发**:每个新功能(审批/子流程/链式触发)都配套完整测试用例,后端 485+ 测试 + 前端 104+ 测试,每次迭代全量回归,确保工程质量。这避免了"加功能破功能"的恶性循环。

5. **真实场景驱动的 bug 修复**:很多 bug 是在实际使用中发现的,如:
   - `--border` 带 alpha 通道导致暗色模式"全是黑"(审查报告定位三层根因)
   - ReactFlow 缺少 Provider 导致 `useReactFlow()` 报错
   - vi.mock 时序变化导致测试失败(`findByText` 替代 `getByText`)
   - 链式触发深度无限制可能导致无限循环(加 MAX_CHAIN_DEPTH=3)
   这些真实问题及其解决过程,都是 TRAE 协作开发的宝贵记录。

6. **DeepSeek 兼容 OpenAI SDK**:只需替换 base_url 即可使用,开发成本低,国内直连速度快。

7. **安全与可观测性并重**:
   - 代码节点 AST 安全检查(阻断 `__class__`/`__bases__` 等危险属性)
   - 沙箱执行 + 10 秒超时(防止恶意代码)
   - 凭证脱敏存储 + API Key/Admin Token 双重认证
   - 结构化日志(JSON 格式)+ 请求链路追踪(X-Request-Id)
   - 失败通知多通道(邮件/微信/钉钉/Slack/Telegram)

8. **性能优化实战**:
   - ReactFlow `onlyRenderVisibleElements` 仅在节点 > 50 时启用(小图保持交互流畅)
   - Vite manualChunks 函数式分包(Windows 路径正斜杠匹配)
   - Dashboard 缓存 TTL 60s + 写操作主动失效
   - list_workflows 用 load_only 限定列避免 N+1 字段冗余
   - Webhook 异步执行 + 立即返回 202(防止超时)
