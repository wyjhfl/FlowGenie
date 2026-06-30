"""场景：销售报价
工作流：数据库查询 → 代码执行 → LLM 生成 → 发送邮件
"""


def get_template() -> dict:
    """返回销售报价的预定义工作流模板"""
    return {
        "scenario": "数据处理",
        "summary": "查询产品数据库，计算价格，生成报价单并发邮件",
        "steps": [
            {
                "id": "step_1",
                "name": "查询产品",
                "tool": "database_query",
                "params": {
                    "connection": "sqlite:///products.db",
                    "query": "SELECT name, price, stock FROM products WHERE category = 'electronics'"
                },
                "description": "查询产品数据库"
            },
            {
                "id": "step_2",
                "name": "计算价格",
                "tool": "code_node",
                "params": {
                    "code": "result = [{'name': p['name'], 'unit_price': p['price'], 'quantity': 1, 'total': p['price'], 'discount': 0.9} for p in input]\nfor r in result:\n    r['final_price'] = round(r['total'] * r['discount'], 2)",
                    "input": "{{step_1.rows}}"
                },
                "description": "计算折扣价格"
            },
            {
                "id": "step_3",
                "name": "生成报价单",
                "tool": "llm_generate",
                "params": {
                    "content_type": "报价单",
                    "topic": "根据以下产品信息生成正式报价单：{{step_2.result}}",
                    "tone": "正式",
                    "language": "zh",
                    "length": "medium"
                },
                "description": "AI 生成报价单文档"
            },
            {
                "id": "step_4",
                "name": "发送邮件",
                "tool": "send_email",
                "params": {
                    "to": "customer@example.com",
                    "subject": "产品报价单",
                    "content": "{{step_3.content}}"
                },
                "description": "发送报价单邮件"
            }
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
            {"from": "step_3", "to": "step_4"}
        ]
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["报价", "销售", "quote", "price", "销售报价", "产品报价"]
