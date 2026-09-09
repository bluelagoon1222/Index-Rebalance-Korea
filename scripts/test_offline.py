#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline end-to-end test: fakes 네이버·WiseReport responses so the whole pipeline runs without network.
Usage: python scripts/test_offline.py
"""
import datetime as dt
import json
import os
import random
import sys
import tempfile
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect  # noqa: E402
from indices import INDICES  # noqa: E402

random.seed(11)
TODAY = dt.datetime.now(collect.KST).date()

# --- synthetic universe -----------------------------------------------------------------------
KOSPI_BIG = [
    ("005930", "삼성전자", 72000, 4300000), ("000660", "SK하이닉스", 250000, 1800000),
    ("373220", "LG에너지솔루션", 380000, 890000), ("207940", "삼성바이오로직스", 780000, 555000),
    ("005380", "현대차", 240000, 500000), ("000270", "기아", 110000, 440000),
    ("068270", "셀트리온", 180000, 390000), ("105560", "KB금융", 110000, 420000),
    ("055550", "신한지주", 62000, 310000), ("035420", "NAVER", 210000, 330000),
    ("012330", "현대모비스", 280000, 260000), ("028260", "삼성물산", 160000, 270000),
    ("051910", "LG화학", 300000, 210000), ("006400", "삼성SDI", 350000, 240000),
    ("035720", "카카오", 45000, 200000), ("015760", "한국전력", 25000, 160000),
    ("032830", "삼성생명", 105000, 210000), ("017670", "SK텔레콤", 58000, 125000),
    ("009150", "삼성전기", 150000, 112000), ("066570", "LG전자", 95000, 155000),
    ("003550", "LG", 88000, 138000), ("034730", "SK", 190000, 137000),
    ("000810", "삼성화재", 380000, 178000), ("086790", "하나금융지주", 78000, 226000),
    ("316140", "우리금융지주", 19000, 140000), ("030200", "KT", 45000, 112000),
    ("010130", "고려아연", 520000, 105000), ("011200", "HMM", 18000, 98000),
    ("018260", "삼성에스디에스", 150000, 116000), ("009540", "HD한국조선해양", 190000, 134000),
]
KOSDAQ_BIG = [
    ("247540", "에코프로비엠", 140000, 137000), ("086520", "에코프로", 75000, 100000),
    ("028300", "HLB", 40000, 52000), ("196170", "알테오젠", 320000, 170000),
    ("058470", "리노공업", 210000, 32000), ("039030", "이오테크닉스", 180000, 22000),
    ("214150", "클래시스", 55000, 35000), ("263750", "펄어비스", 40000, 25000),
    ("035900", "JYP Ent.", 62000, 22000), ("041510", "에스엠", 95000, 22000),
    ("240810", "원익IPS", 32000, 15000), ("140860", "파크시스템스", 210000, 15000),
    ("357780", "솔브레인", 280000, 21000), ("348370", "엔켐", 90000, 18000),
    ("084370", "유진테크", 45000, 12000),
]


def make_universe():
    rows = {"KOSPI": [], "KOSDAQ": []}
    for code, name, close, mcap_eok in KOSPI_BIG:
        rows["KOSPI"].append((code, name, close, mcap_eok))
    for code, name, close, mcap_eok in KOSDAQ_BIG:
        rows["KOSDAQ"].append((code, name, close, mcap_eok))
    # 지수 대상이 아닌 종목들: 필터가 실제로 걸러내는지 확인하기 위해 섞어 넣는다
    rows["KOSPI"] += [
        ("005935", "삼성전자우", 60000, 1580000),      # 우선주 (코드 끝자리 5)
        ("069500", "KODEX 200", 40000, 260000),        # ETF
        ("360750", "TIGER 미국S&P500", 22000, 200000),  # ETF
        ("330590", "이지스레지던스리츠", 5000, 3000),      # 리츠
        ("456780", "대신밸런스제18호스팩", 2000, 300),     # 스팩
        ("500001", "삼성 레버리지 WTI원유 ETN", 9000, 5000),
    ]
    # filler so paging and the 500-stock sanity check are exercised
    for i in range(620):   # 보통주 코드는 끝자리가 0
        rows["KOSPI"].append(("9%04d0" % i, "코스피기타%d" % i, 5000 + i, max(300, 90000 - i * 140)))
    for i in range(900):
        rows["KOSDAQ"].append(("8%04d0" % i, "코스닥기타%d" % i, 3000 + i, max(200, 14000 - i * 15)))
    for mk in rows:
        rows[mk].sort(key=lambda r: -r[3])
    return rows


UNIV = make_universe()
ALL = {c: (c, n, px, eok, mk) for mk in UNIV for (c, n, px, eok) in UNIV[mk]}


def market_sum_html(market, page):
    rows = UNIV[market]
    per = 50
    chunk = rows[(page - 1) * per: page * per]
    trs = ['<tr><th>N</th><th>종목명</th><th>현재가</th><th>전일비</th><th>등락률</th><th>액면가</th>'
           '<th>시가총액</th><th>상장주식수</th><th>외국인비율</th><th>거래량</th><th>PER</th>'
           '<th>ROE</th><th>토론실</th></tr>', '<tr><td colspan="13"></td></tr>']
    for i, (code, name, close, mcap_eok) in enumerate(chunk, 1 + (page - 1) * per):
        shares_k = int(mcap_eok * 100000000 / close / 1000)
        trs.append(
            '<tr><td>%d</td><td><a href="/item/main.naver?code=%s">%s</a></td>'
            '<td>%s</td><td>100</td><td>+0.14%%</td><td>100</td><td>%s</td><td>%s</td>'
            '<td>35.20</td><td>%s</td><td>12.34</td><td>8.10</td><td>-</td></tr>'
            % (i, code, name, "{:,}".format(close), "{:,}".format(mcap_eok),
               "{:,}".format(shares_k), "{:,}".format(random.randint(10000, 9000000))))
    return ('<html><body><div class="box_type_l"><table class="type_2">%s</table></div></body></html>'
            % "".join(trs))


# --- synthetic index holdings ----------------------------------------------------------------
ETF_CODES_FAKE = {"069500", "360750", "102110", "148020", "278530", "122630", "252670",
                  "229200", "232080", "233740", "396500", "488080", "466920"}


def eligible(market):
    return [r for r in UNIV[market]
            if collect.is_common_stock(r[0], r[1], ETF_CODES_FAKE)]


def holdings_for(etf_code):
    if etf_code == "069500":       # KODEX 200 -> KOSPI 상위 200
        pool = eligible("KOSPI")[:200]
    elif etf_code == "229200":     # KODEX 코스닥150
        pool = eligible("KOSDAQ")[:150]
    elif etf_code == "396500":     # TIGER 반도체TOP10
        names = ["삼성전자", "SK하이닉스", "리노공업", "이오테크닉스", "원익IPS", "유진테크",
                 "솔브레인", "삼성전기", "고려아연", "파크시스템스"]
        pool = [r for mk in UNIV for r in UNIV[mk] if r[1] in names]
    else:
        pool = []
    tot = sum(r[3] for r in pool) or 1
    rows = []
    if etf_code == "396500":
        # 실제 지수처럼 상위 2종목이 Cap을 넘어선 상태를 만든다 (합계 100%)
        fixed = {"삼성전자": 28.4, "SK하이닉스": 26.1}
        rest = [r for r in pool if r[1] not in fixed]
        rest_tot = sum(r[3] for r in rest) or 1
        left = 100 - sum(fixed.values())
        for code, name, close, eok_ in pool:
            w = fixed.get(name)
            if w is None:
                w = left * eok_ / rest_tot
            rows.append({"STK_NM_KOR": name, "ETF_WEIGHT": round(w, 4),
                         "AGMT_STK_CNT": int(eok_ * 1000 / close), "TRD_DT": TODAY.isoformat()})
    else:
        for code, name, close, eok_ in pool:
            rows.append({"STK_NM_KOR": name, "ETF_WEIGHT": round(eok_ / tot * 100, 4),
                         "AGMT_STK_CNT": int(eok_ * 1000 / close), "TRD_DT": TODAY.isoformat()})
    rows.append({"STK_NM_KOR": "원화예금", "ETF_WEIGHT": 0.35, "AGMT_STK_CNT": 0,
                 "TRD_DT": TODAY.isoformat()})
    rows.append({"STK_NM_KOR": "존재하지않는종목", "ETF_WEIGHT": 0.1, "AGMT_STK_CNT": 1,
                 "TRD_DT": TODAY.isoformat()})
    return rows


ETF_LIST = [
    {"itemcode": "069500", "itemname": "KODEX 200", "marketSum": 60000, "nav": 40000, "nowVal": 40000},
    {"itemcode": "360750", "itemname": "TIGER 미국S&P500", "marketSum": 200000, "nav": 22000, "nowVal": 22000},
    {"itemcode": "102110", "itemname": "TIGER 200", "marketSum": 25000, "nav": 40000, "nowVal": 40000},
    {"itemcode": "148020", "itemname": "KBSTAR 200", "marketSum": 12000, "nav": 40000, "nowVal": 40000},
    {"itemcode": "278530", "itemname": "KODEX 200TR", "marketSum": 18000, "nav": 40000, "nowVal": 40000},
    {"itemcode": "122630", "itemname": "KODEX 레버리지", "marketSum": 30000, "nav": 20000, "nowVal": 20000},
    {"itemcode": "252670", "itemname": "KODEX 200선물인버스2X", "marketSum": 20000, "nav": 3000, "nowVal": 3000},
    {"itemcode": "229200", "itemname": "KODEX 코스닥150", "marketSum": 9000, "nav": 12000, "nowVal": 12000},
    {"itemcode": "232080", "itemname": "TIGER 코스닥150", "marketSum": 4000, "nav": 12000, "nowVal": 12000},
    {"itemcode": "233740", "itemname": "KODEX 코스닥150레버리지", "marketSum": 8000, "nav": 9000, "nowVal": 9000},
    {"itemcode": "396500", "itemname": "TIGER 반도체TOP10", "marketSum": 15000, "nav": 15000, "nowVal": 15000},
    {"itemcode": "488080", "itemname": "TIGER 반도체TOP10레버리지", "marketSum": 3000, "nav": 8000, "nowVal": 8000},
    {"itemcode": "466920", "itemname": "SOL 반도체TOP10", "marketSum": 2000, "nav": 11000, "nowVal": 11000},
]


class FakeResp:
    def __init__(self, text=None, js=None, status=200):
        self.status_code, self._t, self._j = status, text, js
        self.encoding = None
        self.apparent_encoding = "utf-8"

    def json(self):
        return self._j if self._j is not None else json.loads(self._t)

    @property
    def text(self):
        return self._t

    @property
    def content(self):
        return (self._t or "").encode()


def fake_get(url, headers=None, params=None, timeout=None):
    u = urlparse(url)
    p = params or {}
    if u.netloc == "finance.naver.com":
        if "sise_market_sum" in u.path:
            mk = "KOSPI" if str(p.get("sosok")) == "0" else "KOSDAQ"
            return FakeResp(text=market_sum_html(mk, int(p.get("page", 1))))
        if "etfItemList" in u.path:
            return FakeResp(js={"result": {"etfItemList": ETF_LIST}})
    if u.netloc == "navercomp.wisereport.co.kr":
        rows = holdings_for(p.get("cmp_cd"))
        return FakeResp(text="<html><script>var CU_data = %s;</script></html>"
                             % json.dumps({"grid_data": rows}, ensure_ascii=False))
    if u.netloc == "api.finance.naver.com":
        code = p.get("symbol")
        base = ALL.get(code)
        px = base[2] if base else 10000
        rows = [["날짜", "시가", "고가", "저가", "종가", "거래량", "외국인소진율"]]
        d = dt.datetime.strptime(p["startTime"], "%Y%m%d").date()
        end = dt.datetime.strptime(p["endTime"], "%Y%m%d").date()
        while d <= end:
            if d.weekday() < 5:
                rows.append([d.strftime("%Y%m%d"), px, px, px, px,
                             random.randint(50000, 3000000), 30.0])
            d += dt.timedelta(days=1)
        return FakeResp(text=str(rows).replace("'", '"'))
    raise RuntimeError("unexpected url " + url)


def main():
    collect.requests.get = fake_get
    collect.SLEEP = 0
    tmp = tempfile.mkdtemp()
    collect.DATA = tmp
    sys.argv = ["collect.py"]
    collect.main()

    latest = json.load(open(os.path.join(tmp, "latest.json"), encoding="utf-8"))
    print("\n=== RESULT ===")
    print("universe:", latest["universe"], "| calendar events:", len(latest["calendar"]))
    print("next:", latest["calendar"][0]["family_name"], latest["calendar"][0]["review"],
          "D-%d" % latest["calendar"][0]["d_effective"])
    for ix in latest["indices"]:
        print("\n--", ix["name"], "| 구성", ix.get("member_count"), "| 추종자금",
              round(ix["aum"] / 1e12, 1), "조 (ETF %d개)" % len(ix["aum_etfs"]),
              "| 미매칭", ix.get("unmatched"))
        for r in ix["rows"][:6]:
            print("   %-10s %-14s %s 비중 %+7.3f%%  예상수급 %+8.0f억  거래대금대비 %s일  순위 %s" % (
                r["side"], r["name"], r.get("market") or "", r["weight"], (r["flow"] or 0) / 1e8,
                r.get("days_to_cover"), r.get("rank")))
    # assertions
    assert latest["universe"] > 1400
    st = json.load(open(os.path.join(tmp, "status.json"), encoding="utf-8"))
    assert st["universe_raw"] - st["universe"] >= 6, (st["universe_raw"], st["universe"])
    print("universe filtered:", st["universe_raw"], "->", st["universe"])
    bad = {"삼성전자우", "KODEX 200", "TIGER 미국S&P500", "이지스레지던스리츠",
           "대신밸런스제18호스팩", "삼성 레버리지 WTI원유 ETN"}
    for ix in latest["indices"]:
        offenders = [r["name"] for r in ix["rows"] if r["name"] in bad]
        assert not offenders, (ix["key"], offenders)
        assert not [h for h in ix["holdings"] if h["name"] in bad], ix["key"]
    k2 = next(i for i in latest["indices"] if i["key"] == "kospi200")
    assert k2["member_count"] == 200, k2["member_count"]
    assert abs(k2["aum"] - 115000 * 1e8) < 1e8, k2["aum"]          # 200 + 200TR only
    assert any(r["side"] == "in" for r in k2["rows"]) and any(r["side"] == "out" for r in k2["rows"])
    outs = [r for r in k2["rows"] if r["side"] == "out"]
    assert all(r["flow"] < 0 and r["weight"] < 0 for r in outs), "편출 수급이 0이거나 부호가 잘못됨"
    kq = next(i for i in latest["indices"] if i["key"] == "kosdaq150")
    assert kq["member_count"] == 150
    assert abs(kq["aum"] - 13000 * 1e8) < 1e8, kq["aum"]           # leverage excluded
    semi = next(i for i in latest["indices"] if i["key"] == "semi_top10")
    assert semi["member_count"] == 10
    sells = [r for r in semi["rows"] if r["side"] == "sell"]
    assert any(r["name"] == "삼성전자" for r in sells), "삼성전자 매도 추정이 없음"
    assert all(r["unmatched"] is not None for r in [{"unmatched": i.get("unmatched")} for i in latest["indices"]])
    assert all("존재하지않는종목" in (i.get("unmatched") or []) for i in latest["indices"])
    print("\nALL CHECKS PASSED ->", tmp)
    return tmp


if __name__ == "__main__":
    main()
