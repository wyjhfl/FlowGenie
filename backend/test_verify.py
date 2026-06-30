"""端到端验证脚本"""
import os
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
import httpx
import json

BASE = 'http://127.0.0.1:8000/api'

def test_llm_workflow():
    """测试 LLM 工作流生成（验证空数据保护引导）"""
    print("=" * 60)
    print("测试 1: LLM 工作流生成（验证空数据保护引导）")
    print("=" * 60)
    req = {
        "requirement": "每天早上8点抓取科技新闻生成摘要推送到微信",
        "use_template": False
    }
    try:
        r = httpx.post(f'{BASE}/parse', json=req, timeout=120)
        d = r.json()
        print(f"source: {d['source']}")
        print(f"scenario: {d['scenario']}")
        print(f"steps: {len(d['steps'])}")
        for s in d['steps']:
            print(f"  {s['id']}: {s['name']} ({s['tool']})")
        print("edges:")
        for e in d['edges']:
            cond = e.get('condition', '')
            print(f"  {e['from']} -> {e['to']} {cond}")

        # 检查是否包含 if_else 空数据保护
        has_if_else = any(s['tool'] == 'if_else' for s in d['steps'])
        if has_if_else:
            print("\n✅ 工作流包含 if_else 空数据保护！")
        else:
            print("\n⚠️ 工作流未包含 if_else 空数据保护（LLM 可能未遵循引导）")

        return d
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None

def test_templates():
    """测试所有模板匹配"""
    print("\n" + "=" * 60)
    print("测试 2: 模板匹配（10 个模板）")
    print("=" * 60)
    test_cases = [
        ("每天抓取新闻摘要", "news_summary"),
        ("销售报表数据分析", "sales_report"),
        ("代码提交后code review", "code_review"),
        ("RSS订阅聚合摘要", "rss_summary"),
        ("GitHub Issue 监控", "github_monitor"),
        ("Telegram 定时推送AI资讯", "telegram_push"),
        ("网页监控告警", "web_monitor"),
        ("数据分析报告", "data_analysis"),
        ("帮我审核合同", "contract_review"),
        ("生成销售报价单", "sales_quote"),
    ]
    passed = 0
    for requirement, expected in test_cases:
        req = {"requirement": requirement, "use_template": True}
        try:
            r = httpx.post(f'{BASE}/parse', json=req, timeout=30)
            d = r.json()
            status = "✅" if d['source'] == 'template' and len(d['steps']) > 0 else "❌"
            if status == "✅":
                passed += 1
            print(f"  {status} {requirement} -> {d['scenario']} ({len(d['steps'])} 步骤)")
        except Exception as e:
            print(f"  ❌ {requirement} -> 请求失败: {e}")
    print(f"\n模板匹配结果: {passed}/{len(test_cases)} 通过")

def test_web_scraper_fallback():
    """测试 web_scraper 空数据兜底"""
    print("\n" + "=" * 60)
    print("测试 3: web_scraper 空数据兜底")
    print("=" * 60)
    # 直接调用 web_scraper 工具测试
    import sys
    sys.path.insert(0, '.')
    import asyncio
    from tools.web_scraper import execute

    async def run():
        # 使用一个不存在的 selector 触发回退
        params = {
            "url": "https://news.ycombinator.com",
            "selector": "nonexistent.selector",
            "fields": ["title", "content"]
        }
        try:
            result = await execute(params, None)
            print(f"  title: {result.get('title', 'N/A')[:50]}")
            print(f"  items count: {result.get('count', 0)}")
            print(f"  page_text 长度: {len(result.get('page_text', ''))}")
            if result.get('page_text'):
                print("  ✅ page_text 字段存在且有内容")
            else:
                print("  ❌ page_text 字段缺失或为空")
            if result.get('items'):
                print(f"  ✅ items 兜底成功: {len(result['items'])} 条")
            else:
                print("  ❌ items 为空，兜底失败")
        except Exception as e:
            print(f"  ❌ 测试失败: {e}")

    asyncio.run(run())

def test_llm_summary_empty():
    """测试 llm_summary 空数据容错"""
    print("\n" + "=" * 60)
    print("测试 4: llm_summary 空数据容错")
    print("=" * 60)
    import asyncio
    from tools.llm_summary import execute

    async def run():
        test_cases = [
            ("空字符串", {"text": ""}),
            ("None", {"text": None}),
            ("空数组", {"text": []}),
            ("空数组字符串", {"text": "[]"}),
        ]
        for name, params in test_cases:
            try:
                result = await execute(params, None)
                print(f"  ✅ {name}: summary='{result['summary']}'")
            except Exception as e:
                print(f"  ❌ {name}: 抛异常 {e}")

    asyncio.run(run())

if __name__ == '__main__':
    test_web_scraper_fallback()
    test_llm_summary_empty()
    test_templates()
    test_llm_workflow()
