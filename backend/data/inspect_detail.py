"""详细查看执行结果中的 output 字段"""
import json
import sys


def main(path: str):
    d = json.load(open(path, "r", encoding="utf-8-sig"))
    print("=== DETAIL OUTPUT ===")
    for k, v in d.get("steps_result", {}).items():
        if isinstance(v, dict):
            out = v.get("output", {})
            print(f"\n--- {k} (status={v.get('status')}) ---")
            if isinstance(out, dict):
                for ok, ov in out.items():
                    sv = str(ov)
                    print(f"  {ok}: {sv[:300]}")
            else:
                print(f"  output: {str(out)[:300]}")


if __name__ == "__main__":
    main(sys.argv[1])
