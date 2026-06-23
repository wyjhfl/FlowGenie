"""测试 LLM 工作流拆解"""
from dotenv import load_dotenv
load_dotenv()
from core.llm import chat_json
from core.prompts import PARSE_SYSTEM_PROMPT, build_parse_user_prompt
from core.tool_registry import get_tools_description

sp = PARSE_SYSTEM_PROMPT.format(tools_description=get_tools_description())
up = build_parse_user_prompt("帮我每天监控竞品价格变化，如果降价超过10%就发邮件通知我")
r = chat_json(sp, up, temperature=0.3)

print("scenario:", r.get("scenario", ""))
print("summary:", r.get("summary", ""))
print("steps:", len(r.get("steps", [])))
for s in r.get("steps", []):
    print(f"  {s['id']}: {s['name']} -> {s['tool']}")
print("edges:", r.get("edges", []))
