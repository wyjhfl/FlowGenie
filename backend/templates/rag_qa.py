"""C5: RAG 知识库问答模板

工作流:手动触发 → 向量检索 Top-K 文档 → LLM 基于检索结果生成答案

展示 C5 向量检索/RAG 能力:
1. 用户输入问题 → 向量检索本地知识库(pickle 文件)→ 取 Top-3 相关文档
2. LLM 基于检索到的文档片段 + 用户问题生成 grounded 答案

前置条件:
- 已配置 LLM_API_KEY(用于 embedding 与 LLM 生成)
- 已通过 vector_store_upsert 工具预先写入知识库文档
"""


def get_template() -> dict:
    """返回 RAG 知识库问答的预定义工作流模板"""
    return {
        "scenario": "知识库问答",
        "summary": "检索增强生成(RAG):基于本地向量知识库检索 Top-K 相关文档,LLM 结合检索结果生成有依据的答案",
        "steps": [
            {
                "id": "step_1",
                "name": "手动触发",
                "description": "用户输入问题后触发",
                "tool": "manual_trigger",
                "params": {},
            },
            {
                "id": "step_2",
                "name": "向量检索",
                "description": "用用户问题在本地知识库中检索 Top-3 相关文档",
                "tool": "vector_store_search",
                "params": {
                    "store_path": "vectors/kb.pkl",
                    "query": "{{trigger_data.question}}",
                    "top_k": 3,
                },
            },
            {
                "id": "step_3",
                "name": "RAG 问答生成",
                "description": "LLM 基于检索到的文档片段生成 grounded 答案",
                "tool": "llm_analysis",
                "params": {
                    "data": "{{step_2.results}}",
                    "task": "基于检索到的文档片段回答用户问题;若文档中无相关信息,请明确说明无法回答,不要编造。问题: {{trigger_data.question}}",
                },
            },
        ],
        "edges": [
            {"from": "step_1", "to": "step_2"},
            {"from": "step_2", "to": "step_3"},
        ],
    }


def match_keywords() -> list[str]:
    """用于场景识别的关键词"""
    return ["rag", "知识库", "检索增强", "向量检索", "向量问答", "kb 问答", "knowledge base", "embedding 问答"]
