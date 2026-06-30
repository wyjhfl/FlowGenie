"""详细查看 parse 结果的完整 steps(含 sub_steps)"""
import json
import sys


def main(path: str):
    d = json.load(open(path, "r", encoding="utf-8-sig"))
    print("=== FULL STEPS ===")
    for s in d.get("steps", []):
        print(f"\n--- {s['id']}: {s.get('name','')} (tool={s['tool']}) ---")
        print(json.dumps(s, ensure_ascii=False, indent=2)[:1500])


if __name__ == "__main__":
    main(sys.argv[1])
