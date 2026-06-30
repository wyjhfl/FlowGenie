"""场景16：股价监控告警
工作流：HTTP 请求行情 API → LLM 趋势分析 → switch_branch 涨跌幅路由 → 条件告警推送
"""


def get_template() -> dict:
    """返回股价监控告警的预定义工作流模板"""
    return {
        "scenario": "监控告警",
        "summary": "定时获取股票行情数据，用 LLM 分析趋势，按涨跌幅路由到大涨/大跌/平稳分支，条件触发告警",
        "steps": [
            {
                "id": "step_1",
                "name": "获取行情数据",
                "description": "调用行情 API 获取股票价格",
                "tool": "http_request",
                "params": {
                    "url": "https://api.example.com/stock/AAPL",
                    "method": "GET",
                    "headers": {},
                },
            },
            {
                "id": "step_2",
                "name": "趋势分析",
                "description": "用 LLM 分析行情趋势并给出涨跌判断",
                "tool": "llm_analysis",
                "params": {
                    "data": "{{step_1.body}}",
                    "task": "分析股票涨跌趋势，判断属于大涨、大跌还是平稳，给出简短结论",
                },
            },
            {
                "id": "step_3",
                "name": "涨跌幅路由",
                "description": "按分析结论路由：大涨/大跌走告警，平稳走记录",
                "tool": "switch_branch",
                "params": {
                    "field": "{{step_2.analysis}}",
                    "cases": ["大涨", "大跌", "平稳"],
                },
            },
            {
                "id": "step_4",
                "name": "钉钉告警",
                "description": "大涨或大跌通过钉钉告警",
                "tool": "send_dingtalk",
                "params": {
                    "content": "📈 股价告警\n分析: {{step_2.analysis}}\n行情: {{step_1.body}}",
                    "msg_type": "text",
                },
            },
            {
                "id": "step_5",
                "name": "Telegram 通知",
                "description": "同时通过 Telegram 通知",
                "tool": "send_telegram",
                "params": {
                    "chat_id": "stock_alert_chat",
                    "text": "股价告警: {{step_2.analysis}}",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4", "condition": "大涨"},
            {"from": "step_3", "to": "step_4", "condition": "大跌"},
            {"from": "step_4", "to": "step_5"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["股价", "股票", "stock", "行情", "涨跌", "股市", "alert", "股价监控", "股票告警"]
