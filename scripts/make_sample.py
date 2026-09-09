#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""화면 확인용 샘플 데이터 생성 (data/latest.json). 실제 수집 전에 UI를 점검하는 용도."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect  # noqa: E402
import test_offline  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def main():
    collect.requests.get = test_offline.fake_get
    collect.SLEEP = 0
    collect.DATA = DATA
    sys.argv = ["collect.py"]
    collect.main()
    p = os.path.join(DATA, "latest.json")
    d = json.load(open(p, encoding="utf-8"))
    d["sample"] = True
    d["generated_at"] += " (SAMPLE)"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    st = os.path.join(DATA, "status.json")
    s = json.load(open(st, encoding="utf-8"))
    s["message"] = "sample data"
    with open(st, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.remove(os.path.join(DATA, "state.json"))
    print("sample written:", p)


if __name__ == "__main__":
    main()
