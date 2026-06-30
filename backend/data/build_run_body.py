"""构造 /run 请求体:基于 parse 结果,可覆盖某些参数
用法: python build_run_body.py <parse_file> <out_file> [overrides_json]
overrides_json 示例: '{"step_1.params.path":"inputs/sales_leads.json"}'
"""
import json
import sys


def set_nested(obj: dict, dotted_key: str, value):
    keys = dotted_key.split(".")
    cur = obj
    for k in keys[:-1]:
        if k.isdigit() and isinstance(cur, list):
            cur = cur[int(k)]
        else:
            cur = cur[k]
    last = keys[-1]
    if last.isdigit() and isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def main(parse_file: str, out_file: str, overrides_json: str = ""):
    d = json.load(open(parse_file, "r", encoding="utf-8-sig"))
    body = {
        "steps": d["steps"],
        "edges": d.get("edges", []),
        "on_failure": "continue",
    }
    if overrides_json:
        overrides = json.loads(overrides_json)
        for k, v in overrides.items():
            # 支持 step_<n>.params.<key> 形式
            if k.startswith("step_") and ".params." in k:
                step_id, param_key = k.split(".params.", 1)
                for s in body["steps"]:
                    if s["id"] == step_id:
                        s["params"][param_key] = v
                        break
            elif k == "on_failure":
                body["on_failure"] = v
            else:
                set_nested(body, k, v)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
    print(f"OK -> {out_file} (steps={len(body['steps'])})")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
