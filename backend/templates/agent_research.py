"""F1: Agent 自主调研模板

工作流:手动触发 → Function Calling 智能体(LLM 自主调用 http_request + web_scraper + llm_summary 循环推理)
展示 Function Calling 能力:LLM 根据用户问题自主决定抓取哪些网页、如何总结。
"""


def get_template() -> dict:
    """返回 Agent 自主调研的预定义工作流模板"""
    return {
        "scenario": "智能体",
        "summary": "LLM 作为智能体自主调用工具(HTTP 请求/网页抓取/摘要)完成任务,循环推理直到给出答案",
        "steps": [
            {
                "id": "step_1",
                "name": "手动触发",
                "description": "用户输入问题后触发 Agent",
                "tool": "manual_trigger",
                "params": {},
            },
            {
                "id": "step_2",
                "name": "Agent 自主调研",
                "description": "LLM 自主决策调用 http_request/web_scraper/llm_summary 工具,循环推理给出最终答案",
                "tool": "function_call",
                "params": {
                    "prompt": "{{trigger_data.prompt}}",
                    "tools": ["http_request", "web_scraper", "llm_summary"],
                    "max_iterations": 10,
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["agent", "智能体", "自主调研", "function calling", "agent 调研", "自主决策", "自动调研"]
