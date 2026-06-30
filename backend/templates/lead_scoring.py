"""场景14：销售线索评分
工作流：读取线索数据 → LLM 抽取字段 → LLM 评分分级 → switch_branch 路由 → 通知
"""


def get_template() -> dict:
    """返回销售线索评分的预定义工作流模板"""
    return {
        "scenario": "销售运营",
        "summary": "读取销售线索数据，用 LLM 抽取关键字段并评分分级，按等级路由到不同通知渠道",
        "steps": [
            {
                "id": "step_1",
                "name": "读取线索数据",
                "description": "读取本地线索 JSON 文件",
                "tool": "file_read",
                "params": {
                    "path": "input/leads.json",
                    "format": "json",
                },
            },
            {
                "id": "step_2",
                "name": "抽取线索字段",
                "description": "从线索数据中抽取公司、规模、行业、预算等字段",
                "tool": "llm_extract",
                "params": {
                    "text": "{{step_1.content}}",
                    "schema": "公司名称, 公司规模, 行业, 预算, 联系人, 职位",
                    "instruction": "请从销售线索数据中抽取结构化信息",
                },
            },
            {
                "id": "step_3",
                "name": "线索评分分级",
                "description": "按抽取的字段给线索分级(A/B/C/D)",
                "tool": "llm_classify",
                "params": {
                    "text": "{{step_2.entities}}",
                    "categories": "A,B,C,D",
                    "task": "topic",
                },
            },
            {
                "id": "step_4",
                "name": "分支路由",
                "description": "按等级路由：A 级走飞书实时通知，其他走邮件",
                "tool": "switch_branch",
                "params": {
                    "field": "{{step_3.category}}",
                    "cases": ["A", "B", "C", "D"],
                },
            },
            {
                "id": "step_5",
                "name": "A 级线索飞书通知",
                "description": "A 级线索通过飞书机器人实时通知销售",
                "tool": "feishu_api",
                "params": {
                    "content": "🔥 A 级线索\n{{step_2.entities}}\n分级: {{step_3.category}}",
                    "msg_type": "text",
                },
            },
            {
                "id": "step_6",
                "name": "其他线索邮件记录",
                "description": "B/C/D 级线索通过邮件汇总",
                "tool": "send_email",
                "params": {
                    "to": "sales@example.com",
                    "subject": "线索分级汇总",
                    "content": "{{step_2.entities}}\n分级: {{step_3.category}}",
                    "content_type": "plain",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4"},
            {"from": "step_4", "to": "step_5", "condition": "A"},
            {"from": "step_4", "to": "step_6", "condition": "default"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["线索", "评分", "lead", "scoring", "crm", "客户分级", "销售线索", "线索评分"]
