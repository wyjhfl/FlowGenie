"""测试 LLM 连通性"""
from dotenv import load_dotenv
load_dotenv()
from core.llm import chat, chat_json, has_api_key

print("1. API Key configured:", has_api_key())

print("\n2. Testing basic chat...")
try:
    result = chat(
        "You are a helpful assistant.",
        "Say hello in Chinese, just one sentence.",
        temperature=0.3,
    )
    print("   LLM Response:", result)
except Exception as e:
    print("   Error:", type(e).__name__, str(e))

print("\n3. Testing JSON chat (workflow parse)...")
try:
    result = chat_json(
        "You are a workflow parser. Return JSON with fields: greeting, language.",
        "Say hello and tell me what language you used.",
        temperature=0.3,
    )
    print("   JSON Response:", result)
except Exception as e:
    print("   Error:", type(e).__name__, str(e))
