"""导出为可执行 Python 脚本 - 将工作流转为可独立运行的 .py 文件"""
import json
import re
from datetime import datetime


# ===== 各工具函数实现（简化版，每个函数接收 params: dict）=====

TOOL_IMPLEMENTATIONS: dict[str, str] = {

    "http_request": r'''
async def http_request(params):
    # 发起 HTTP/HTTPS 请求
    import httpx
    url = params.get("url", "")
    method = params.get("method", "GET").upper()
    headers = params.get("headers") or {}
    body = params.get("body")
    if not url:
        raise ValueError("url 参数不能为空")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        kwargs = {"headers": headers}
        if body is not None and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, (dict, list)):
                kwargs["json"] = body
            else:
                kwargs["content"] = str(body)
        resp = await client.request(method, url, **kwargs)
    try:
        parsed = resp.json()
    except Exception:
        parsed = resp.text
    return {"status_code": resp.status_code, "headers": dict(resp.headers), "body": parsed}
''',

    "web_scraper": r'''
async def web_scraper(params):
    # 抓取网页内容，支持 CSS 选择器提取（含 page_text 兜底）
    import httpx
    from bs4 import BeautifulSoup
    url = params.get("url", "")
    selector = params.get("selector", "body")
    fields = params.get("fields") or ["title"]
    if not url:
        raise ValueError("url 参数不能为空")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"抓取失败: HTTP {resp.status_code}")
    soup = BeautifulSoup(resp.text, "html.parser")
    page_title = soup.title.string.strip() if soup.title and soup.title.string else ""
    page_text = soup.get_text(separator="\n", strip=True)[:5000]
    elements = soup.select(selector) or soup.select("body")
    items = []
    for elem in elements[:50]:
        item = {}
        for field in fields:
            if field in ("href", "link", "url"):
                link = elem.find("a")
                item[field] = link.get("href", "") if link else ""
            else:
                item[field] = elem.get_text(strip=True)[:500]
        items.append(item)
    if not items and page_text:
        items = [{"title": page_title or "页面内容", "content": page_text[:500]}]
    return {"title": page_title, "url": url, "items": items, "count": len(items), "page_text": page_text}
''',

    "llm_summary": r'''
async def llm_summary(params):
    # 调用 LLM 生成文本摘要（含空数据容错）
    text = params.get("text", "")
    max_length = params.get("max_length", 500)
    language = params.get("language", "zh")
    if text is None or text == "" or text == []:
        return {"summary": "无内容可摘要", "original_length": 0}
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, default=str)
    if not text.strip():
        return {"summary": "无内容可摘要", "original_length": 0}
    lang_hint = "中文" if language == "zh" else "English"
    system_prompt = f"你是摘要生成助手。请用{lang_hint}生成不超过 {max_length} 字的摘要，只输出摘要内容。"
    user_prompt = f"请摘要以下内容：\n\n{text}"
    summary = _llm_chat(system_prompt, user_prompt, temperature=0.3)
    return {"summary": summary.strip(), "original_length": len(text)}
''',

    "llm_analysis": r'''
async def llm_analysis(params):
    # 调用 LLM 进行数据分析（含空数据容错）
    data = params.get("data", "")
    task = params.get("task", "分析数据趋势并给出洞察")
    if data is None or data == "" or data == []:
        return {"analysis": "无数据可分析"}
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False, default=str)
    if not data.strip():
        return {"analysis": "无数据可分析"}
    system_prompt = "你是数据分析专家。请根据给定任务分析数据，给出结构化的分析结果。"
    user_prompt = f"任务：{task}\n\n数据：\n{data}"
    analysis = _llm_chat(system_prompt, user_prompt, temperature=0.3)
    return {"analysis": analysis.strip()}
''',

    "llm_generate": r'''
async def llm_generate(params):
    # 调用 LLM 生成报告/邮件/文章/文案（含空数据容错）
    content_type = params.get("content_type", "report")
    topic = params.get("topic", "")
    tone = params.get("tone", "professional")
    language = params.get("language", "zh")
    length = params.get("length", "")
    if topic is None or topic == "" or topic == []:
        return {"content": "无主题内容", "content_type": content_type}
    if not isinstance(topic, str):
        topic = json.dumps(topic, ensure_ascii=False, default=str)
    if not topic.strip():
        return {"content": "无主题内容", "content_type": content_type}
    lang_hint = "中文" if language == "zh" else "English"
    type_desc = {"report": "结构化报告", "email": "邮件", "article": "文章", "copywriting": "营销文案"}.get(content_type, "结构化内容")
    tone_desc = {"professional": "专业", "casual": "轻松", "formal": "正式"}.get(tone, "专业")
    length_hint = f"字数约 {length}。" if length else ""
    system_prompt = f"你是内容创作助手。请用{lang_hint}生成{tone_desc}风格的{type_desc}。{length_hint}只输出最终内容。"
    user_prompt = f"请围绕以下主题生成{type_desc}：\n\n{topic}"
    content = _llm_chat(system_prompt, user_prompt, temperature=0.7)
    return {"content": content.strip(), "content_type": content_type}
''',

    "llm_review": r'''
async def llm_review(params):
    # 调用 LLM 对代码进行 Review（含空数据容错）
    code = params.get("code", "")
    focus = params.get("focus") or ["bug", "security", "performance", "style"]
    if code is None or code == "" or code == []:
        return {"review": "无代码可审查", "issues_count": 0}
    if not isinstance(code, str):
        code = json.dumps(code, ensure_ascii=False, default=str)
    if not code.strip():
        return {"review": "无代码可审查", "issues_count": 0}
    focus_str = "、".join(focus) if isinstance(focus, list) else str(focus)
    system_prompt = f"你是资深代码审查专家。请从以下维度审查代码：{focus_str}。先列出问题（编号），再给出建议。"
    user_prompt = f"请审查以下代码：\n\n```\n{code}\n```"
    review = _llm_chat(system_prompt, user_prompt, temperature=0.3)
    issues_count = len(re.findall(r"^\s*\d+[\.\)]\s", review, re.MULTILINE))
    return {"review": review.strip(), "issues_count": issues_count}
''',

    "send_email": r'''
async def send_email(params):
    # 通过 SMTP 发送邮件（配置从环境变量读取）
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    to = params.get("to", "")
    subject = params.get("subject", "FlowGenie 工作流通知")
    content = params.get("content", "")
    content_type = params.get("content_type", "plain")
    if not to:
        raise ValueError("to 参数不能为空")
    if not content:
        return {"success": False, "message": "邮件内容为空，已跳过发送"}
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    if not smtp_host or not smtp_user:
        raise ValueError("未配置 SMTP，请设置环境变量 SMTP_HOST/SMTP_USER/SMTP_PASS")
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(content, content_type, "utf-8"))
    server = None
    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to], msg.as_string())
        return {"success": True, "message": f"邮件已发送至 {to}"}
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass
''',

    "send_wechat": r'''
async def send_wechat(params):
    # 企业微信机器人推送（Webhook URL 从环境变量或参数读取）
    import httpx
    webhook_url = params.get("webhook_url", "") or os.getenv("WECHAT_WEBHOOK", "")
    content = params.get("content", "")
    msg_type = params.get("msg_type", "markdown")
    if not webhook_url:
        raise ValueError("企业微信 Webhook 未配置，请设置环境变量 WECHAT_WEBHOOK")
    if not content:
        return {"success": False, "response": {}}
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)
    if msg_type == "markdown":
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
    else:
        payload = {"msgtype": "text", "text": {"content": content}}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)
    result = resp.json()
    if not isinstance(result, dict) or result.get("errcode", 0) != 0:
        raise RuntimeError(f"企业微信推送失败: {result}")
    return {"success": True, "response": result}
''',

    "send_slack": r'''
async def send_slack(params):
    # Slack Webhook 推送
    import httpx
    webhook_url = params.get("webhook_url", "") or os.getenv("SLACK_WEBHOOK", "")
    text = params.get("text", params.get("content", ""))
    if not webhook_url:
        raise ValueError("Slack Webhook 未配置，请设置环境变量 SLACK_WEBHOOK")
    if not text:
        return {"success": False, "response": ""}
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, default=str)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json={"text": text})
    if resp.status_code != 200 or resp.text != "ok":
        raise RuntimeError(f"Slack 推送失败: {resp.status_code} {resp.text}")
    return {"success": True, "response": resp.text}
''',

    "send_dingtalk": r'''
async def send_dingtalk(params):
    # 钉钉机器人推送
    import httpx
    webhook_url = params.get("webhook_url", "") or os.getenv("DINGTALK_WEBHOOK", "")
    content = params.get("content", "")
    msg_type = params.get("msg_type", "text")
    at_mobiles = params.get("at_mobiles") or []
    if not webhook_url:
        raise ValueError("钉钉 Webhook 未配置，请设置环境变量 DINGTALK_WEBHOOK")
    if not content:
        return {"success": False, "response": {}}
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)
    if msg_type == "markdown":
        payload = {"msgtype": "markdown", "markdown": {"title": "FlowGenie 通知", "text": content}}
    else:
        payload = {"msgtype": "text", "text": {"content": content}}
    if at_mobiles:
        payload["at"] = {"atMobiles": at_mobiles if isinstance(at_mobiles, list) else [at_mobiles], "isAtAll": False}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)
    result = resp.json()
    if not isinstance(result, dict) or result.get("errcode", 0) != 0:
        raise RuntimeError(f"钉钉推送失败: {result}")
    return {"success": True, "response": result}
''',

    "send_telegram": r'''
async def send_telegram(params):
    # Telegram Bot 推送
    import httpx
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = params.get("chat_id", "")
    text = params.get("text", "")
    parse_mode = params.get("parse_mode", "text")
    if not bot_token:
        raise ValueError("Telegram Bot Token 未配置，请设置环境变量 TELEGRAM_BOT_TOKEN")
    if not chat_id:
        raise ValueError("chat_id 参数不能为空")
    if not text:
        return {"message_id": 0, "chat_id": str(chat_id), "date": 0}
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, default=str)
    parse_mode_map = {"text": None, "markdown": "Markdown", "html": "HTML"}
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    tg_mode = parse_mode_map.get(parse_mode)
    if tg_mode:
        payload["parse_mode"] = tg_mode
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
    result = resp.json()
    if isinstance(result, dict) and result.get("ok"):
        return {"message_id": result["result"]["message_id"], "chat_id": str(chat_id), "date": result["result"].get("date", 0)}
    raise RuntimeError(f"Telegram API 错误: {result.get('description', resp.text) if isinstance(result, dict) else resp.text}")
''',

    "file_read": r'''
async def file_read(params):
    # 读取本地文件，支持 text/json 格式
    path = params.get("path", "")
    fmt = params.get("format", "text")
    if not path:
        raise ValueError("path 参数不能为空")
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    size = os.path.getsize(path)
    if fmt == "json":
        with open(path, "r", encoding="utf-8") as f:
            content = json.load(f)
    else:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    return {"content": content, "size": size, "path": path}
''',

    "file_write": r'''
async def file_write(params):
    # 将内容写入本地文件
    path = params.get("path", "")
    content = params.get("content", "")
    fmt = params.get("format", "text")
    if not path:
        raise ValueError("path 参数不能为空")
    if not content:
        return {"success": False, "path": path, "size": 0}
    if fmt == "json" and isinstance(content, (dict, list)):
        text = json.dumps(content, ensure_ascii=False, indent=2)
    else:
        text = str(content)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return {"success": True, "path": path, "size": os.path.getsize(path)}
''',

    "code_node": r'''
async def code_node(params):
    # 执行 Python 代码（安全沙箱，用 input 变量访问输入，用 result= 设置输出）
    code = params.get("code", "")
    input_data = params.get("input")
    if not code or not code.strip():
        raise ValueError("code 参数不能为空")
    # AST 安全检查：拒绝危险属性访问
    safety_error = _check_code_safety(code)
    if safety_error:
        return {"result": None, "success": False, "error": safety_error}
    # 危险模块导入检查（前缀匹配 import/from 语句）
    for module in _FORBIDDEN_IMPORTS:
        if f"import {module}" in code or f"from {module}" in code:
            return {"result": None, "success": False, "error": f"禁止导入 {module} 模块"}
    safe_globals = {
        "__builtins__": _CODE_NODE_BUILTINS,
        "input": input_data,
        "result": None,
    }
    try:
        await asyncio.wait_for(
            asyncio.to_thread(exec, code, safe_globals),
            timeout=10
        )
        return {"result": safe_globals.get("result"), "success": True, "error": None}
    except asyncio.TimeoutError:
        raise TimeoutError("代码执行超时（10秒限制）")
    except Exception as e:
        return {"result": None, "success": False, "error": f"{type(e).__name__}: {e}"}
''',

    "if_else": r'''
async def if_else(params):
    # 条件分支判断，返回 {result, branch: "true"|"false"}
    field = params.get("field")
    operator = params.get("operator", "eq")
    value = params.get("value")
    try:
        result = _eval_condition(field, operator, value)
    except Exception:
        result = False
    return {"result": result, "branch": "true" if result else "false"}


def _eval_condition(field, operator, value):
    # 条件求值（支持 18 个操作符）
    if operator == "eq":
        return field == value
    elif operator == "ne":
        return field != value
    elif operator in ("gt", "ge", "lt", "le"):
        try:
            if field is None:
                return False
            if operator == "gt":
                return field > value
            elif operator == "ge":
                return field >= value
            elif operator == "lt":
                return field < value
            else:
                return field <= value
        except TypeError:
            return False
    elif operator == "is_empty":
        return field is None or field == "" or field == [] or field == {}
    elif operator == "is_not_empty":
        return not (field is None or field == "" or field == [] or field == {})
    elif operator == "is_null":
        return field is None or field == "" or field == []
    elif operator == "is_not_null":
        return not (field is None or field == "" or field == [])
    elif operator == "contain":
        return field is not None and str(value) in str(field)
    elif operator == "not_contain":
        return field is None or str(value) not in str(field)
    elif operator in ("len_gt", "len_ge", "len_lt", "len_le"):
        try:
            n = len(field)
            v = int(value)
            if operator == "len_gt":
                return n > v
            elif operator == "len_ge":
                return n >= v
            elif operator == "len_lt":
                return n < v
            else:
                return n <= v
        except (TypeError, ValueError):
            return False
    elif operator == "startwith":
        return field is not None and str(field).startswith(str(value))
    elif operator == "endwith":
        return field is not None and str(field).endswith(str(value))
    raise ValueError(f"不支持的 operator: {operator}")
''',

    "rss_reader": r'''
async def rss_reader(params):
    # 读取 RSS/Atom 订阅源
    import httpx
    import xml.etree.ElementTree as ET
    feed_url = params.get("feed_url", "")
    limit = params.get("limit", 10)
    if not feed_url:
        raise ValueError("feed_url 参数不能为空")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(feed_url, headers={"User-Agent": "Mozilla/5.0 FlowGenie/1.0"})
    if resp.status_code != 200:
        raise RuntimeError(f"获取订阅源失败: HTTP {resp.status_code}")
    root = ET.fromstring(resp.content)

    def _local(tag):
        return tag.split("}")[-1] if "}" in tag else tag

    def _text(elem, name):
        for e in elem:
            if _local(e.tag) == name:
                return (e.text or "").strip()
        return ""

    entries = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    items = []
    for entry in entries[:limit]:
        link = _text(entry, "link")
        if not link:
            for e in entry:
                if _local(e.tag) == "link" and e.get("href"):
                    link = e.get("href")
                    break
        items.append({
            "title": _text(entry, "title"),
            "link": link,
            "published": _text(entry, "pubDate") or _text(entry, "published") or _text(entry, "date"),
            "summary": _text(entry, "description") or _text(entry, "summary") or _text(entry, "content"),
        })
    return {"items": items, "count": len(items)}
''',

    "github_api": r'''
async def github_api(params):
    # 调用 GitHub REST API
    import httpx
    endpoint = params.get("endpoint", "")
    owner = params.get("owner", "")
    repo = params.get("repo", "")
    method = params.get("method", "GET").upper()
    query_params = params.get("params") or {}
    token = params.get("token", "") or os.getenv("GITHUB_TOKEN", "")
    if not endpoint:
        raise ValueError("endpoint 参数不能为空")
    if owner:
        endpoint = endpoint.replace("{owner}", owner)
    if repo:
        endpoint = endpoint.replace("{repo}", repo)
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    url = f"https://api.github.com{endpoint}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "FlowGenie/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30) as client:
        kwargs = {"headers": headers}
        if query_params and method == "GET":
            kwargs["params"] = query_params
        elif query_params and method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = query_params
        resp = await client.request(method, url, **kwargs)
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    rate_limit = resp.headers.get("X-RateLimit-Remaining", "0")
    return {"status_code": resp.status_code, "body": body, "rate_limit_remaining": int(rate_limit) if str(rate_limit).isdigit() else 0}
''',

    "database_query": r'''
async def database_query(params):
    # 执行 SQL 查询（SQLite 用标准库，其他数据库需 sqlalchemy）
    connection = params.get("connection", "") or os.getenv("DATABASE_URL", "")
    query = params.get("query", "")
    if not connection:
        raise ValueError("数据库连接未配置，请设置环境变量 DATABASE_URL")
    if not query:
        raise ValueError("query 参数不能为空")
    if connection.startswith("sqlite"):
        import sqlite3
        db_path = connection.replace("sqlite:///", "").replace("sqlite://", "")
        conn = sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(query)
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
            columns = list(rows[0].keys()) if rows else []
            return {"rows": rows, "count": len(rows), "columns": columns, "message": f"查询成功，返回 {len(rows)} 行"}
        finally:
            conn.close()
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        raise RuntimeError("非 SQLite 数据库需要安装 sqlalchemy: pip install sqlalchemy")
    engine = create_engine(connection)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            if result.returns_rows:
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
                return {"rows": rows, "count": len(rows), "columns": columns, "message": f"查询成功，返回 {len(rows)} 行"}
            else:
                conn.commit()
                return {"rows": [], "count": 0, "columns": [], "message": "执行成功（无返回行）"}
    finally:
        engine.dispose()
''',

    "data_transform": r'''
async def data_transform(params):
    # 数据转换：去重/字段映射/类型转换/条件过滤
    data = params.get("data")
    operations = params.get("operations") or []
    if data is None:
        raise ValueError("data 参数不能为空")
    if not operations:
        raise ValueError("operations 参数不能为空")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("data 为字符串但无法解析为 JSON")
    is_single = isinstance(data, dict)
    rows = [data] if is_single else data
    if not isinstance(rows, list):
        raise ValueError("data 必须是 list[dict] 或 dict")
    for op in operations:
        op_type = op.get("type", "")
        if op_type == "deduplicate":
            key = op.get("key", "")
            seen = set()
            new_rows = []
            for row in rows:
                val = row.get(key)
                if isinstance(val, (list, dict)):
                    val = json.dumps(val, ensure_ascii=False, sort_keys=True)
                if val not in seen:
                    seen.add(val)
                    new_rows.append(row)
            rows = new_rows
        elif op_type == "map_fields":
            mapping = op.get("mapping", {})
            rows = [{mapping.get(k, k): v for k, v in row.items()} for row in rows]
        elif op_type == "convert_type":
            fields = op.get("fields", {})
            for row in rows:
                for field, target in fields.items():
                    if field in row:
                        try:
                            if target == "int":
                                row[field] = int(float(row[field])) if row[field] != "" else 0
                            elif target == "float":
                                row[field] = float(row[field]) if row[field] != "" else 0.0
                            elif target == "str":
                                row[field] = str(row[field])
                        except (ValueError, TypeError):
                            pass
        elif op_type == "filter":
            field = op.get("field", "")
            operator = op.get("operator", "eq")
            value = op.get("value")
            new_rows = []
            for row in rows:
                val = row.get(field)
                match = False
                if operator == "eq":
                    match = val == value
                elif operator == "ne":
                    match = val != value
                elif operator == "gt":
                    try:
                        match = val is not None and val > value
                    except TypeError:
                        match = False
                elif operator == "lt":
                    try:
                        match = val is not None and val < value
                    except TypeError:
                        match = False
                elif operator == "contains":
                    match = val is not None and str(value) in str(val)
                if match:
                    new_rows.append(row)
            rows = new_rows
    result = rows[0] if is_single and rows else (rows if not is_single else None)
    return {"data": result, "count": len(rows)}
''',

    "chart_generator": r'''
async def chart_generator(params):
    # 生成图表（HTML 表格 / ASCII 柱状图 / ASCII 饼图）
    from html import escape
    data = params.get("data")
    chart_type = params.get("chart_type", "table")
    title = params.get("title", "数据图表")
    x_field = params.get("x_field", "")
    y_field = params.get("y_field", "")
    if data is None:
        raise ValueError("data 参数不能为空")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("data 为字符串但无法解析为 JSON")
    if not isinstance(data, list):
        raise ValueError("data 必须是 list[dict]")
    data_points = len(data)
    if chart_type == "table":
        if not data:
            chart_html = f"<div><h3>{escape(title)}</h3><p>无数据</p></div>"
        else:
            columns = []
            seen = set()
            for row in data:
                for k in row.keys():
                    if k not in seen:
                        seen.add(k)
                        columns.append(k)
            header = "".join(f"<th>{escape(c)}</th>" for c in columns)
            rows_html = ""
            for row in data:
                cells = ""
                for col in columns:
                    val = row.get(col, "")
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val, ensure_ascii=False)
                    cells += f"<td>{escape(str(val))}</td>"
                rows_html += f"<tr>{cells}</tr>"
            chart_html = f'<div><h3>{escape(title)}</h3><table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;"><thead><tr>{header}</tr></thead><tbody>{rows_html}</tbody></table></div>'
    elif chart_type in ("bar", "pie"):
        if not data:
            chart_html = f"{title}\n无数据"
        else:
            first = data[0]
            if isinstance(first, dict):
                keys = list(first.keys())
                x_field = x_field or (keys[0] if keys else "")
                y_field = y_field or (keys[1] if len(keys) > 1 else keys[0] if keys else "")
            points = []
            for row in data:
                label = str(row.get(x_field, "")) if x_field else ""
                try:
                    val = float(row.get(y_field, 0))
                except (ValueError, TypeError):
                    val = 0
                points.append((label, val))
            if chart_type == "bar":
                max_val = max(abs(v) for _, v in points) or 1
                max_label = max(len(l) for l, _ in points) if points else 0
                lines = [title, ""]
                for label, val in points:
                    bar_len = int(abs(val) / max_val * 40)
                    lines.append(f"{label.ljust(max_label)} | {'█' * bar_len} {val}")
                chart_html = "\n".join(lines)
            else:
                total = sum(v for _, v in points) or 1
                symbols = "●▲■◆★♥♣♠"
                lines = [title, ""]
                for i, (label, val) in enumerate(points):
                    pct = val / total * 100
                    lines.append(f"{symbols[i % len(symbols)]} {label}: {val} ({pct:.1f}%)")
                lines += ["", f"总计: {total}"]
                chart_html = "\n".join(lines)
    else:
        raise ValueError(f"不支持的 chart_type: {chart_type}")
    return {"chart_html": chart_html, "chart_type": chart_type, "data_points": data_points}
''',

}


# ===== LLM 调用辅助函数（仅在使用 LLM 工具时包含）=====

LLM_CHAT_HELPER = r'''
def _llm_chat(system_prompt, user_prompt, temperature=0.3, max_tokens=2000):
    # 调用 LLM（OpenAI 兼容接口），失败时返回提示信息而非抛异常
    from openai import OpenAI
    if not LLM_API_KEY:
        return "[LLM_API_KEY 未配置，请设置环境变量 LLM_API_KEY]"
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM 调用失败: {e}]"
'''


# ===== code_node 安全沙箱辅助（仅在使用 code_node 时包含）=====

CODE_NODE_SAFETY_HELPER = r'''
# === code_node 安全沙箱辅助 ===
import ast as _ast

# 禁止导入的模块列表（含子模块，前缀匹配）
_FORBIDDEN_IMPORTS = [
    "os", "subprocess", "sys", "socket", "shutil", "pathlib",
    "ctypes", "multiprocessing", "threading", "asyncio",
    "importlib", "builtins",
]

# 危险属性集合（防止通过属性访问逃逸沙箱，与 code_node.py 保持一致）
_DANGEROUS_ATTRS = {
    # 原有 13 个危险属性
    "__class__", "__bases__", "__subclasses__", "__globals__",
    "__code__", "__init__", "__dict__", "__mro__", "__module__",
    "__import__", "__builtins__", "__loader__", "__spec__",
    # 新增：traceback / frame 相关（用于逃逸沙箱获取调用栈）
    "__traceback__", "tb_frame", "tb_lineno", "tb_next",
    "f_globals", "f_locals", "f_builtins", "f_code", "f_back",
    # 新增：方法/函数绑定对象相关
    "__self__", "__getattribute__", "__func__", "__wrapped__",
    # 新增：generator / coroutine 帧相关
    "gi_frame", "gi_code", "cr_frame", "cr_code",
    # 新增：pickle / 序列化绕过相关
    "__reduce__", "__reduce_ex__", "__subclasshook__",
}


def _check_code_safety(code):
    """AST 检查危险属性访问，返回错误信息或 None"""
    try:
        tree = _ast.parse(code)
    except SyntaxError as e:
        return f"语法错误: {e}"
    dangerous_found = []
    for node in _ast.walk(tree):
        # 检查属性访问 x.__class__ 等
        if isinstance(node, _ast.Attribute):
            if node.attr in _DANGEROUS_ATTRS and node.attr not in dangerous_found:
                dangerous_found.append(node.attr)
    if dangerous_found:
        return f"禁止访问危险属性: {', '.join(dangerous_found)}"
    return None


# 受限 __builtins__：仅暴露安全的内置函数
_CODE_NODE_BUILTINS = {
    "print": print, "len": len, "str": str, "int": int, "float": float,
    "bool": bool, "list": list, "dict": dict, "range": range,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "sorted": sorted, "min": min, "max": max, "sum": sum, "abs": abs,
    "round": round, "any": any, "all": all,
    "isinstance": isinstance, "issubclass": issubclass, "type": type,
}
'''


# ===== 变量插值 =====

RESOLVE_VARIABLES_CODE = r'''
# === 变量插值 ===
def resolve_variables(value, context):
    """递归解析 {{step_id.field}} 变量引用，支持 str/dict/list"""
    if isinstance(value, str):
        return _resolve_str(value, context)
    elif isinstance(value, dict):
        return {k: resolve_variables(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_variables(item, context) for item in value]
    return value


def _resolve_str(text, context):
    """解析字符串中的变量引用，支持 default 过滤器"""
    pattern = r"\{\{\s*([\w_.]+)\s*(?:\|\s*default\s*:\s*[\"']([^\"']*)[\"'])?\s*\}\}"
    matches = list(re.finditer(pattern, text))
    if not matches:
        return text
    if len(matches) == 1 and text.strip() == matches[0].group(0):
        return _get_var(matches[0].group(1), matches[0].group(2), context)
    for m in matches:
        replacement = _get_var(m.group(1), m.group(2), context)
        text = text.replace(m.group(0), str(replacement))
    return text


def _get_var(path, default, context):
    """根据路径获取变量值: step_id / step_id.field / step_id.field.sub
    特殊: trigger.xxx 获取触发器数据
          item / index 获取 loop 子流程变量
    未找到时返回 default（若提供）否则空字符串
    """
    parts = path.split(".")
    first = parts[0]

    # 特殊变量: trigger（触发器数据）
    if first == "trigger":
        value = context.get("trigger", {})
        for part in parts[1:]:
            if isinstance(value, dict):
                if part not in value:
                    return default if default is not None else ""
                value = value[part]
            else:
                return default if default is not None else ""
        return value

    # 特殊变量: item (loop 子流程中当前迭代项)
    if first == "item":
        value = context.get("item")
        if value is None:
            return default if default is not None else ""
        if len(parts) == 1:
            return value
        for part in parts[1:]:
            if isinstance(value, dict):
                if part not in value:
                    return default if default is not None else ""
                value = value[part]
            elif isinstance(value, list):
                try:
                    idx = int(part)
                    if 0 <= idx < len(value):
                        value = value[idx]
                    else:
                        return default if default is not None else ""
                except (ValueError, IndexError):
                    return default if default is not None else ""
            else:
                return default if default is not None else ""
        return value

    # 特殊变量: index (loop 子流程中当前迭代索引)
    if first == "index":
        value = context.get("index")
        if value is None:
            return default if default is not None else ""
        return value

    # 步骤输出变量
    step_id = first
    output = context.get(step_id)
    if output is None:
        return default if default is not None else ""
    if len(parts) == 1:
        return output
    val = output
    for part in parts[1:]:
        if isinstance(val, dict):
            val = val.get(part)
        elif isinstance(val, list):
            try:
                val = val[int(part)]
            except (ValueError, IndexError):
                return default if default is not None else ""
        else:
            return default if default is not None else ""
        if val is None:
            return default if default is not None else ""
    return val
'''


# ===== 执行引擎 =====

EXECUTE_ENGINE_CODE = r'''
# === 执行引擎 ===
async def execute_workflow(steps, edges, trigger_data=None):
    """按拓扑顺序执行工作流，支持变量插值与条件分支（简化版，不支持并发）
    :param trigger_data: 触发器传入的初始数据（如 Webhook payload），可通过 {{trigger.xxx}} 引用
    """
    step_map = {s["id"]: s for s in steps if s.get("id")}
    step_ids = set(step_map.keys())

    # 构建邻接表与入度
    out_edges = {sid: [] for sid in step_ids}
    in_degree = {sid: 0 for sid in step_ids}
    for edge in edges:
        f = edge.get("from")
        t = edge.get("to")
        if f in step_ids and t in step_ids:
            out_edges[f].append(edge)
            in_degree[t] += 1

    # 拓扑排序（Kahn 算法）
    queue = deque(sorted([sid for sid in step_ids if in_degree[sid] == 0]))
    order = []
    pending = dict(in_degree)
    while queue:
        sid = queue.popleft()
        order.append(sid)
        for edge in out_edges[sid]:
            to_id = edge.get("to")
            pending[to_id] -= 1
            if pending[to_id] == 0:
                queue.append(to_id)

    # 执行
    context = {"trigger": trigger_data or {}}
    results = {}
    activated = {sid: (in_degree[sid] == 0) for sid in step_ids}

    for sid in order:
        step = step_map[sid]
        tool = step.get("tool", "")

        # 条件分支未命中：跳过（传播跳过，不激活后继）
        if not activated.get(sid, True):
            results[sid] = {"output": None, "status": "skipped", "error": "条件分支未命中"}
            continue

        # 触发器：仅作起点标记，不执行实际逻辑
        if tool in ("schedule_trigger", "manual_trigger", "webhook_trigger"):
            output = {"message": f"触发器: {step.get('name', tool)}"}
            context[sid] = output
            results[sid] = {"output": output, "status": "success"}
            _activate_successors(sid, out_edges, activated, None)
            continue

        # 解析参数（变量插值）
        raw_params = step.get("params", {})
        resolved_params = resolve_variables(raw_params, context)

        # 执行工具
        branch = None
        try:
            if tool == "if_else":
                output = await if_else(resolved_params)
                branch = output.get("branch")
            elif tool in TOOL_EXECUTORS:
                output = await TOOL_EXECUTORS[tool](resolved_params)
            else:
                output = {"error": f"工具 '{tool}' 未实现，请手动补充"}
            context[sid] = output
            results[sid] = {"output": output, "status": "success"}
            print(f"  [✓] {step.get('name', sid)} ({tool})")
        except Exception as e:
            results[sid] = {"output": None, "status": "failed", "error": str(e)}
            print(f"  [✗] {step.get('name', sid)} ({tool}): {e}")

        # 激活后继节点
        _activate_successors(sid, out_edges, activated, branch)

    return results


def _activate_successors(sid, out_edges, activated, branch):
    """根据分支结果激活后继节点（条件分支仅激活匹配边）"""
    for edge in out_edges.get(sid, []):
        to_id = edge.get("to")
        condition = edge.get("condition", "")
        if branch is not None:
            if condition == branch:
                activated[to_id] = True
        elif condition == "exception":
            pass
        else:
            activated[to_id] = True


# 工具执行器映射（自动收集已定义的工具函数）
TOOL_EXECUTORS = {}
for _name in ("http_request", "web_scraper", "llm_summary", "llm_analysis",
              "llm_generate", "llm_review", "send_email", "send_wechat",
              "send_slack", "send_dingtalk", "send_telegram", "file_read",
              "file_write", "code_node", "rss_reader", "github_api",
              "database_query", "data_transform", "chart_generator"):
    _func = globals().get(_name)
    if _func is not None:
        TOOL_EXECUTORS[_name] = _func
'''


# 需要使用 LLM 的工具集合
_LLM_TOOLS = {"llm_summary", "llm_analysis", "llm_generate", "llm_review"}


def _build_header(workflow_name: str, timestamp: str) -> str:
    """构建脚本头部（shebang + docstring + imports）"""
    return (
        "#!/usr/bin/env python3\n"
        '"""\n'
        f"FlowGenie 工作流: {workflow_name}\n"
        f"自动生成于 {timestamp}\n"
        "依赖: pip install httpx openai beautifulsoup4  (按实际使用的工具按需安装)\n"
        '"""\n'
        "import asyncio\n"
        "import json\n"
        "import re\n"
        "import os\n"
        "from collections import deque\n"
    )


def _build_config() -> str:
    """构建配置区（LLM 环境变量）"""
    return (
        "# === 配置 ===\n"
        'LLM_API_KEY = os.getenv("LLM_API_KEY", "")\n'
        'LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://apihub.agnes-ai.com/v1")\n'
        'LLM_MODEL = os.getenv("LLM_MODEL", "agnes-2.0-flash")\n'
    )


def _build_main(steps_json: str, edges_json: str) -> str:
    """构建主入口（内嵌 STEPS/EDGES 为 JSON 字符串，运行时 json.loads）"""
    steps_repr = repr(steps_json)
    edges_repr = repr(edges_json)
    return (
        "# === 主入口 ===\n"
        'if __name__ == "__main__":\n'
        '    _trigger_raw = os.getenv("TRIGGER_DATA", "")\n'
        '    _trigger_data = None\n'
        '    if _trigger_raw:\n'
        '        try:\n'
        '            _trigger_data = json.loads(_trigger_raw)\n'
        '        except json.JSONDecodeError:\n'
        '            _trigger_data = None\n'
        f"    STEPS = json.loads({steps_repr})\n"
        f"    EDGES = json.loads({edges_repr})\n"
        '    print("=" * 50)\n'
        '    print("开始执行 FlowGenie 工作流")\n'
        '    print("=" * 50)\n'
        "    result = asyncio.run(execute_workflow(STEPS, EDGES, trigger_data=_trigger_data))\n"
        '    print()\n'
        '    print("=" * 50)\n'
        '    print("执行结果:")\n'
        '    print("=" * 50)\n'
        "    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))\n"
    )


def export_to_python_script(workflow: dict) -> str:
    """
    将工作流导出为可独立运行的 Python 脚本字符串。
    :param workflow: 工作流字典，含 steps/edges/summary 等字段
    :return: 完整的 Python 脚本字符串
    """
    workflow_name = (workflow.get("summary") or "FlowGenie 工作流")[:80]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 精简 steps/edges，只保留执行所需字段
    clean_steps = []
    for s in workflow.get("steps", []):
        clean_steps.append({
            "id": s.get("id", ""),
            "name": s.get("name", ""),
            "tool": s.get("tool", ""),
            "params": s.get("params", {}),
        })
    clean_edges = []
    for e in workflow.get("edges", []):
        edge = {"from": e.get("from", ""), "to": e.get("to", "")}
        if e.get("condition"):
            edge["condition"] = e["condition"]
        clean_edges.append(edge)

    # 收集工作流中实际使用的工具（仅限已实现的）
    used_tools = []
    seen = set()
    for s in clean_steps:
        t = s.get("tool", "")
        if t in TOOL_IMPLEMENTATIONS and t not in seen:
            seen.add(t)
            used_tools.append(t)

    # 判断是否需要 LLM 辅助函数
    need_llm = bool(_LLM_TOOLS & set(used_tools))

    # 判断是否需要 code_node 安全沙箱辅助
    need_code_safety = "code_node" in used_tools

    # 组装完整脚本
    parts = [
        _build_header(workflow_name, timestamp),
        _build_config(),
    ]
    if need_llm:
        parts.append(LLM_CHAT_HELPER)
    if need_code_safety:
        parts.append(CODE_NODE_SAFETY_HELPER)
    for t in used_tools:
        parts.append(TOOL_IMPLEMENTATIONS[t])
    parts.append(RESOLVE_VARIABLES_CODE)
    parts.append(EXECUTE_ENGINE_CODE)

    steps_json = json.dumps(clean_steps, ensure_ascii=False, indent=2)
    edges_json = json.dumps(clean_edges, ensure_ascii=False, indent=2)
    parts.append(_build_main(steps_json, edges_json))

    return "\n\n".join(parts)
