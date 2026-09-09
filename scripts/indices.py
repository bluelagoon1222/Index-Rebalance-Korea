# -*- coding: utf-8 -*-
"""
Tracked indices and the ETFs used as their data proxy.

Why ETFs: index constituent lists and weights are not published in a login-free machine-readable form,
but the physical ETF that tracks an index discloses its full holdings every day. So the representative
ETF's holdings are used as the constituent list, and the ETFs that track the same index are summed to
estimate how much passive money follows it.

aum_include / aum_exclude are matched against the ETF name after the brand prefix is stripped.
Leverage and inverse products are excluded: they replicate with futures, not with the shares themselves.
"""

BRANDS = ("KODEX", "TIGER", "KBSTAR", "HANARO", "KOSEF", "ARIRANG", "ACE", "SOL", "RISE", "PLUS",
          "TIMEFOLIO", "WOORI", "BNK", "DAISHIN", "히어로즈", "마이다스", "파워", "TREX", "FOCUS",
          "KIWOOM", "삼성", "미래에셋", "한국투자")

EXCLUDE_ALWAYS = r"레버리지|인버스|２ｘ|2X|선물|액티브|커버드콜|채권|혼합"

INDICES = [
    {
        "key": "kospi200",
        "name": "KOSPI 200",
        "market": "KOSPI",
        "size": 200,
        "etf": "069500",                 # KODEX 200 - 구성종목·비중 원천
        "aum_include": r"^200(\s*TR)?$",
        "aum_default": 57.2e12,          # 미래에셋 리서치 2026-06 기준 추정치
        "family": "krx_regular",
        "cap": None,
        "note": "산업군별 누적 유동시총 85%·최소 상장 6개월 요건. 편입 후보는 시가총액 순위 기준 추정입니다.",
    },
    {
        "key": "kosdaq150",
        "name": "KOSDAQ 150",
        "market": "KOSDAQ",
        "size": 150,
        "etf": "229200",                 # KODEX 코스닥150
        "aum_include": r"^코스닥\s*150(\s*TR)?$",
        "aum_default": 10.0e12,
        "family": "krx_regular",
        "cap": None,
        "note": "11개 산업군별로 선정하며 금융업도 포함됩니다. 편입 후보는 시가총액 순위 기준 추정입니다.",
    },
    {
        "key": "semi_top10",
        "name": "FnGuide 반도체 TOP10",
        "market": "ALL",
        "size": 10,
        "etf": "396500",                 # TIGER 반도체TOP10
        "aum_include": r"^반도체\s*TOP\s*10(\s*TR)?$",
        "aum_default": 2.0e12,
        "family": "fnguide_sector",
        # 상위 2종목 각 25%, 나머지 8종목이 50%를 유동시총 가중
        "cap": {"top2": 25.0, "rest_total": 50.0, "hard": 30.0},
        "note": "상위 2종목을 각 25%로 되돌리는 정기변경이 삼성전자·SK하이닉스 매도 물량의 원인입니다.",
    },
]

INDEX_BY_KEY = {i["key"]: i for i in INDICES}


def strip_brand(name):
    n = (name or "").strip()
    for b in BRANDS:
        if n.upper().startswith(b.upper()):
            return n[len(b):].strip()
    return n
