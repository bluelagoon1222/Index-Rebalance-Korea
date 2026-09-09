#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Index-Rebalance-Korea collector.

Estimates, for each tracked index, which stocks are likely to be added or removed at the next regular
review and how much passive buying or selling that would mechanically create.

Sources (all login-free)
  * 네이버 금융 시가총액 페이지      전종목 종가·시가총액·상장주식수·거래량
  * 네이버 금융 ETF 목록 API        지수를 추종하는 ETF의 순자산 합계 (패시브 자금 규모 추정)
  * WiseReport ETF 구성내역         지수 구성종목과 비중 (물리적 복제 ETF의 보유내역)
  * 네이버 시세 JSON                최근 거래대금 (수급 부담을 거래일수로 환산)

Outputs (data/)
  latest.json   화면이 읽는 산출물
  status.json   마지막 실행 요약
  state.json    스냅샷 이력 (순위 변화 추적용)

Caveats that the site states on screen
  * 지수 산출에 쓰이는 유동시가총액을 공개 경로로 얻을 수 없어 전체 시가총액을 대용치로 씁니다.
  * 산업군별 누적시총·상장기간 등 세부 요건은 반영하지 않은 순위 기반 추정입니다.
  * 패시브 자금 규모는 ETF 순자산 합계이며, 인덱스펀드·연금 등 비상장 추종자금은 제외됩니다.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from collections import defaultdict

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calendar_rules as CAL  # noqa: E402
from indices import INDICES, strip_brand, EXCLUDE_ALWAYS  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SLEEP = 0.08

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
NV = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "ko-KR,ko;q=0.9",
      "Referer": "https://finance.naver.com/"}
WR = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://finance.naver.com/"}

T0 = time.time()


def log(*a):
    print(dt.datetime.now(KST).strftime("%H:%M:%S"), *a, flush=True)


def elapsed_min():
    return (time.time() - T0) / 60.0


def to_int(v):
    s = re.sub(r"[^0-9\-]", "", str(v if v is not None else ""))
    return int(s) if s not in ("", "-") else None


def to_float(v):
    s = re.sub(r"[^0-9.\-]", "", str(v if v is not None else ""))
    try:
        return float(s)
    except ValueError:
        return None


def ymd(d):
    return d.strftime("%Y%m%d")


def norm_name(s):
    """Match a holding name to a listed name: drop spaces, punctuation and share-class suffixes."""
    s = re.sub(r"\s+", "", str(s or ""))
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace("㈜", "").replace("(주)", "")
    s = re.sub(r"보통주$|우선주$", "", s)
    return s.upper()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, **({"separators": (",", ":")} if compact else {"indent": 1}))
    os.replace(tmp, path)


class Http:
    """requests wrapper with per-host fail-fast so a dead host cannot consume the whole run."""

    def __init__(self):
        self.calls = defaultdict(int)
        self.fails = defaultdict(int)

    def get(self, url, headers=None, params=None, tries=3, mode="json", timeout=25):
        host = url.split("/")[2]
        if self.fails[host] >= 5 and self.calls[host] % 10 != 0:
            tries, timeout = 1, 10
        last = None
        for i in range(tries):
            try:
                self.calls[host] += 1
                r = requests.get(url, headers=headers or {}, params=params, timeout=timeout)
                if r.status_code != 200:
                    raise RuntimeError("HTTP %s" % r.status_code)
                if mode == "json":
                    out = r.json()
                elif mode == "text":
                    r.encoding = r.apparent_encoding or "euc-kr"
                    out = r.text
                else:
                    out = r.content
                self.fails[host] = 0
                time.sleep(SLEEP)
                return out
            except Exception as e:  # noqa
                last = e
                time.sleep(1.5 * (i + 1))
        self.fails[host] += 1
        if self.fails[host] == 5:
            log("host degraded (fail-fast):", host)
        raise RuntimeError("GET failed %s %s: %s" % (url, params, last))


# ----------------------------------------------------------------------------------------------
# 1) universe: every listed stock with close / market cap / shares / volume
# ----------------------------------------------------------------------------------------------
MARKET_SOSOK = {"KOSPI": 0, "KOSDAQ": 1}


def parse_market_sum(html):
    """Parse 네이버 시가총액 table. Columns are located by header text, not by position, because the
    visible column set is configurable."""
    m = re.search(r'<table[^>]*class="[^"]*type_2[^"]*"[^>]*>(.*?)</table>', html, flags=re.S)
    body = m.group(1) if m else html
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S)
    header, out = None, []
    for tr in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)
        if not cells:
            continue
        texts = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in cells]
        if header is None and any("시가총액" in t for t in texts):
            header = {re.sub(r"\s+", "", t): i for i, t in enumerate(texts)}
            continue
        if header is None:
            continue
        code = None
        cm = re.search(r"/item/main\.n(?:hn|aver)\?code=(\d{6})", tr)
        if cm:
            code = cm.group(1)
        if not code:
            continue

        def col(*names):
            for n in names:
                i = header.get(n)
                if i is not None and i < len(texts):
                    return texts[i]
            return None

        name = col("종목명") or ""
        if not name:
            nm = re.search(r"/item/main\.n(?:hn|aver)\?code=\d{6}\"[^>]*>([^<]+)<", tr)
            name = nm.group(1).strip() if nm else ""
        mcap_eok = to_int(col("시가총액"))          # 억원
        shares_k = to_int(col("상장주식수"))        # 천주
        out.append({
            "code": code,
            "name": name,
            "close": to_int(col("현재가")),
            "mcap": mcap_eok * 100000000 if mcap_eok else None,
            "shares": shares_k * 1000 if shares_k else None,
            "volume": to_int(col("거래량")),
            "foreign_pct": to_float(col("외국인비율")),
        })
    return out


# 지수 구성 대상이 아닌 종목: 우선주(종목코드 끝자리가 0이 아님), ETF·ETN, 스팩, 리츠.
# 네이버 시가총액 페이지는 이들을 모두 섞어서 주므로 걸러내지 않으면 시총 순위와 편입 후보가 오염된다.
# 주의: '리츠'는 '메리츠금융지주'의 부분문자열이므로 이름 끝에 올 때만 부동산투자회사로 판단한다.
INELIGIBLE_NAME = re.compile(r"스팩|기업인수목적|위탁관리부동산|ETN|레버리지|인버스|선물|리츠$")
# ETF 목록 API에서 빠진 상품이 있어도 걸러지도록, ETF 전용 브랜드로 시작하는 이름은 제외한다.
# (한글 브랜드나 '삼성'처럼 회사명과 겹치는 접두어는 쓰지 않는다)
ETF_BRAND = re.compile(r"^(KODEX|TIGER|KBSTAR|HANARO|KOSEF|ARIRANG|ACE|SOL|RISE|PLUS|TIMEFOLIO"
                       r"|TREX|FOCUS|KIWOOM)\s", re.I)


def is_common_stock(code, name, etf_codes):
    if not code or len(code) != 6 or code[-1] != "0":
        return False          # 우선주·신주인수권 등 (보통주는 끝자리 0)
    if code in etf_codes:
        return False          # ETF
    name = name or ""
    if INELIGIBLE_NAME.search(name) or ETF_BRAND.match(name):
        return False
    return True


def fetch_universe(h, market):
    """All pages of the market-cap ranking for one market."""
    out, page, sosok, quiet = {}, 1, MARKET_SOSOK[market], 0
    while page <= 80:
        html = h.get("https://finance.naver.com/sise/sise_market_sum.naver", NV,
                      params={"sosok": sosok, "page": page}, mode="text")
        rows = parse_market_sum(html)
        if not rows:
            break                      # 데이터 행이 없으면 마지막 페이지
        fresh = [r for r in rows if r["code"] not in out]
        if not fresh:
            quiet += 1
            if quiet >= 2:             # 같은 내용이 두 번 연속이면 끝난 것으로 본다
                break
        else:
            quiet = 0
        for r in fresh:
            r["market"] = market
            out[r["code"]] = r
        page += 1
    log("universe", market, len(out), "listings in", page - 1, "pages")
    return out


# ----------------------------------------------------------------------------------------------
# 2) ETF list -> passive AUM per index
# ----------------------------------------------------------------------------------------------
def fetch_etf_list(h):
    js = h.get("https://finance.naver.com/api/sise/etfItemList.nhn", NV)
    items = js.get("result", {}).get("etfItemList", []) or []
    out = []
    for i in items:
        eok = to_float(i.get("marketSum"))  # 억원
        out.append({"code": i.get("itemcode"), "name": (i.get("itemname") or "").strip(),
                    "aum": eok * 100000000 if eok else None,
                    "nav": to_float(i.get("nav")), "close": to_float(i.get("nowVal"))})
    log("etf list:", len(out))
    return out


def match_aum(etfs, idx):
    """ETFs that physically track this index, and their combined net assets."""
    inc = re.compile(idx["aum_include"], re.I)
    exc = re.compile(EXCLUDE_ALWAYS, re.I)
    hits = []
    for e in etfs:
        if not e["name"] or exc.search(e["name"]):
            continue
        if inc.search(strip_brand(e["name"])):
            hits.append(e)
    total = sum(e["aum"] or 0 for e in hits)
    return hits, total


# ----------------------------------------------------------------------------------------------
# 3) index constituents from the representative ETF's disclosed holdings
# ----------------------------------------------------------------------------------------------
WR_PAGE = "https://navercomp.wisereport.co.kr/v2/ETF/index.aspx"


def fetch_holdings(h, etf_code):
    html = h.get(WR_PAGE, WR, params={"cmp_cd": etf_code}, mode="text")
    m = re.search(r"var\s+CU_data\s*=\s*(\{.*?\});", html, flags=re.S)
    if not m:
        raise RuntimeError("CU_data not found for %s" % etf_code)
    grid = json.loads(m.group(1)).get("grid_data", []) or []
    rows, date = [], None
    for g in grid:
        name = (g.get("STK_NM_KOR") or "").strip()
        if not name:
            continue
        date = date or re.sub(r"[^0-9]", "", g.get("TRD_DT") or "") or None
        rows.append({"name": name, "weight": to_float(g.get("ETF_WEIGHT")) or 0.0,
                     "shares": to_int(g.get("AGMT_STK_CNT"))})
    return rows, date


CASHLIKE = re.compile(r"원화예금|예금|CD|국고|통안|현금|설정현금|미수금|RP")


def normalize_weights(holdings):
    """ETF 보유내역은 현금성 자산 때문에 합이 100%가 안 되므로 주식분만 100%로 환산한다."""
    tot = sum(hd.get("weight") or 0 for hd in holdings)
    if tot <= 0:
        return holdings
    for hd in holdings:
        hd["weight_raw"] = hd.get("weight")
        hd["weight"] = (hd.get("weight") or 0) / tot * 100
    return holdings


def resolve_holdings(rows, universe):
    """Attach a stock code to each holding; drop cash-like lines."""
    by_name = {}
    for code, u in universe.items():
        by_name.setdefault(norm_name(u["name"]), code)
    out, unmatched, fuzzy = [], [], []
    for r in rows:
        if CASHLIKE.search(r["name"]):
            continue
        nm = norm_name(r["name"])
        code = by_name.get(nm)
        if not code and len(nm) >= 4:
            # 사명 표기가 조금 다른 경우(분할·상호변경 직후 등)를 위한 유일 접두 일치
            cand = [c for n, c in by_name.items() if len(n) >= 4 and (n.startswith(nm) or nm.startswith(n))]
            if len(set(cand)) == 1:
                code = cand[0]
                fuzzy.append("%s -> %s" % (r["name"], universe[code]["name"]))
        if not code:
            unmatched.append(r["name"])
            continue
        u = universe[code]
        out.append({**r, "code": code, "name": u["name"], "mcap": u["mcap"], "market": u["market"],
                    "close": u["close"]})
    return out, unmatched, fuzzy


# ----------------------------------------------------------------------------------------------
# 4) recent turnover for candidates
# ----------------------------------------------------------------------------------------------
def naver_history(h, symbol, start, end):
    txt = h.get("https://api.finance.naver.com/siseJson.naver", NV,
                params={"symbol": symbol, "requestType": "1", "startTime": ymd(start),
                        "endTime": ymd(end), "timeframe": "day"}, mode="text")
    txt = re.sub(r",\s*([\]\}])", r"\1", txt.strip().replace("'", '"'))
    rows = json.loads(txt)
    out = []
    for r in rows[1:]:
        if len(r) < 6:
            continue
        close, vol = to_float(r[4]), to_float(r[5])
        if close and vol is not None:
            out.append((str(r[0]), close, vol))
    return out


def avg_turnover(h, code, today, days=20):
    """Average daily turnover in KRW over the last `days` trading days."""
    rows = naver_history(h, code, today - dt.timedelta(days=int(days * 2.2) + 10), today)
    rows = rows[-days:]
    if not rows:
        return None
    return sum(c * v for _, c, v in rows) / len(rows)


# ----------------------------------------------------------------------------------------------
# 5) candidate screening and passive flow
# ----------------------------------------------------------------------------------------------
def screen_krx(idx, holdings, universe, aum, n_show=15):
    """편입·편출 후보: 시가총액 순위 기준. 지수 규모(size)를 경계선으로 삼는다."""
    members = {hd["code"] for hd in holdings}
    pool = [u for u in universe.values()
            if (idx["market"] == "ALL" or u["market"] == idx["market"]) and u.get("mcap")]
    pool.sort(key=lambda u: -u["mcap"])
    for rank, u in enumerate(pool, 1):
        u["rank"] = rank

    index_mcap = sum(u["mcap"] for u in pool if u["code"] in members) or 1
    # ETF 보유내역의 비중은 소수 둘째 자리까지만 공시돼 소형 구성종목이 0.00~0.01%로 뭉개진다.
    # KOSPI200·코스닥150은 시가총액 가중 지수이므로 수급 추정은 시총 기준 비중으로 계산하고,
    # 공시 비중은 대조용으로만 함께 표시한다.
    weight_by_code = {hd["code"]: hd["weight"] for hd in holdings}

    outs = sorted([u for u in pool if u["code"] in members], key=lambda u: -u["rank"])[:n_show]
    ins = [u for u in pool if u["code"] not in members][:n_show * 3]
    # 편입 후보는 현재 구성종목 최하위 시총보다 큰 종목을 우선 노출
    floor = min((u["mcap"] for u in pool if u["code"] in members), default=0)
    ins = ([u for u in ins if u["mcap"] > floor] or ins)[:n_show]

    def add_row(u, side):
        w = weight_by_code.get(u["code"])
        # weight is the signed change in index weight, so the page can recompute flows from any
        # assumed AUM as aum * weight / 100 without needing to know the side.
        if side == "in":
            nw = u["mcap"] / (index_mcap + u["mcap"]) * 100
        else:
            nw = -(u["mcap"] / index_mcap * 100)
        flow = aum * nw / 100
        return {"code": u["code"], "name": u["name"], "market": u["market"], "rank": u["rank"],
                "mcap": u["mcap"], "close": u["close"], "side": side,
                "weight": round(nw, 4), "flow": int(flow), "cur_weight": w}

    rows = [add_row(u, "in") for u in ins] + [add_row(u, "out") for u in outs]
    for r in rows:  # 경계선(현 구성종목 최소 시총) 대비 여유
        r["gap_pct"] = round((r["mcap"] / floor - 1) * 100, 1) if floor else None
    return {
        "index_mcap": index_mcap,
        "member_count": len(members),
        "floor_rank": max((u["rank"] for u in pool if u["code"] in members), default=None),
        "floor_mcap": floor,
        "rows": rows,
    }


def screen_cap(idx, holdings, aum):
    """FnGuide 섹터 TOP10 계열: 정기변경 때 상위 2종목을 각 25%로 되돌리고
    나머지는 50%를 유동시총 가중으로 나눠 갖는다. 현재 비중과의 차이가 예상 수급."""
    cap = idx["cap"]
    hs = sorted([hd for hd in holdings if hd.get("weight")], key=lambda x: -x["weight"])
    if not hs:
        return {"rows": [], "index_mcap": 0}
    top2, rest = hs[:2], hs[2:]
    rest_mcap = sum(hd.get("mcap") or 0 for hd in rest) or 1
    rows = []
    for i, hd in enumerate(hs):
        if i < 2:
            target = cap["top2"]
        else:
            target = cap["rest_total"] * (hd.get("mcap") or 0) / rest_mcap
        diff = target - hd["weight"]
        rows.append({"code": hd["code"], "name": hd["name"], "market": hd.get("market"),
                     "mcap": hd.get("mcap"), "close": hd.get("close"),
                     "cur_weight": round(hd["weight"], 4), "target_weight": round(target, 4),
                     "weight": round(diff, 4), "flow": int(aum * diff / 100),
                     "side": "buy" if diff > 0 else "sell",
                     "over_cap": hd["weight"] > cap["hard"]})
    rows.sort(key=lambda r: r["flow"])
    return {"rows": rows, "index_mcap": sum(hd.get("mcap") or 0 for hd in hs),
            "member_count": len(hs)}


# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=float, default=40.0)
    ap.add_argument("--turnover-days", type=int, default=20)
    ap.add_argument("--rows", type=int, default=15, help="편입·편출 후보 표시 개수")
    args = ap.parse_args()

    today = dt.datetime.now(KST).date()
    h = Http()
    status = {"ok": True, "message": "", "started": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")}
    state = load_json(os.path.join(DATA, "state.json"), {"snapshots": {}})
    prev = load_json(os.path.join(DATA, "latest.json"), {})

    # ETF 목록을 먼저 받아 둔다: 추종자금 집계에도 쓰고, 전종목 목록에서 ETF를 걸러내는 데도 쓴다.
    etfs = []
    try:
        etfs = fetch_etf_list(h)
    except Exception as e:  # noqa
        log("etf list failed:", e)
    etf_codes = {e["code"] for e in etfs if e.get("code")}

    # universe
    raw_universe = {}
    try:
        for mk in ("KOSPI", "KOSDAQ"):
            raw_universe.update(fetch_universe(h, mk))
    except Exception as e:  # noqa
        log("universe failed:", e)
    universe = {c: u for c, u in raw_universe.items()
                if is_common_stock(c, u.get("name"), etf_codes) and u.get("mcap")}
    # 안전장치: '보통주는 종목코드 끝자리 0' 규칙이 이 목록에 맞지 않아 대부분이 걸러졌다면
    # 그 규칙만 빼고 ETF·ETN·스팩·리츠 제외만 적용한다. 잘못된 가정으로 사이트가 비는 것을 막는다.
    if raw_universe and len(universe) < len(raw_universe) * 0.4:
        log("WARNING: 끝자리 규칙으로 %d/%d만 남아 규칙을 완화합니다"
            % (len(universe), len(raw_universe)))
        universe = {c: u for c, u in raw_universe.items()
                    if c not in etf_codes and u.get("mcap")
                    and not INELIGIBLE_NAME.search(u.get("name") or "")
                    and not ETF_BRAND.match(u.get("name") or "")}
        status["message"] = "종목코드 규칙이 맞지 않아 우선주 제외를 생략했습니다(순위에 우선주가 섞일 수 있음)."
    log("universe filtered: %d -> %d (우선주·ETF·ETN·스팩·리츠 %d개 제외)"
        % (len(raw_universe), len(universe), len(raw_universe) - len(universe)))
    if len(universe) < 500:
        status.update({"ok": False, "message": "전종목 시가총액 수집 실패(%d건) — 직전 데이터를 유지합니다." % len(universe)})
        log("ERROR: universe too small, keeping previous data")
        save_json(os.path.join(DATA, "status.json"), {**status, "finished": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                                                      "minutes": round(elapsed_min(), 1)})
        return

    out_indices = []
    turnover_cache = {}
    for idx in INDICES:
        rec = {k: idx[k] for k in ("key", "name", "market", "size", "family", "note")}
        rec["etf"] = idx["etf"]
        try:
            raw, pdf_date = fetch_holdings(h, idx["etf"])
            holdings, unmatched, fuzzy = resolve_holdings(raw, universe)
            holdings = normalize_weights(holdings)
            if fuzzy:
                log("name matched loosely:", "; ".join(fuzzy[:5]))
        except Exception as e:  # noqa
            log("holdings failed", idx["key"], e)
            old = next((i for i in (prev.get("indices") or []) if i.get("key") == idx["key"]), None)
            if old:
                old["stale"] = True
                out_indices.append(old)
            continue
        hits, aum_auto = match_aum(etfs, idx)
        aum = aum_auto or idx["aum_default"]
        rec.update({
            "pdf_date": pdf_date,
            "etf_name": next((e["name"] for e in etfs if e["code"] == idx["etf"]), idx["etf"]),
            "aum": int(aum), "aum_auto": int(aum_auto), "aum_default": int(idx["aum_default"]),
            "aum_etfs": [{"code": e["code"], "name": e["name"], "aum": int(e["aum"] or 0)}
                         for e in sorted(hits, key=lambda x: -(x["aum"] or 0))],
            "unmatched": unmatched[:10], "fuzzy": fuzzy[:10],
            "holdings": [{"code": hd["code"], "name": hd["name"], "weight": round(hd["weight"], 4),
                          "mcap": hd["mcap"]} for hd in holdings],
        })
        if idx["cap"]:
            rec.update(screen_cap(idx, holdings, aum))
            rec["cap"] = idx["cap"]
        else:
            rec.update(screen_krx(idx, holdings, universe, aum, args.rows))

        # turnover for the rows we will show
        for r in rec.get("rows", []):
            if elapsed_min() > args.budget_min:
                break
            code = r["code"]
            if code not in turnover_cache:
                try:
                    turnover_cache[code] = avg_turnover(h, code, today, args.turnover_days)
                except Exception as e:  # noqa
                    log("turnover failed", code, e)
                    turnover_cache[code] = None
            t = turnover_cache[code]
            r["turnover"] = int(t) if t else None
            r["days_to_cover"] = round(abs(r["flow"]) / t, 2) if t and r.get("flow") else None

        # rank drift vs the previous snapshot
        snap = state["snapshots"].get(idx["key"]) or {}
        for r in rec.get("rows", []):
            old_rank = (snap.get("ranks") or {}).get(r["code"])
            r["rank_prev"] = old_rank
            if old_rank and r.get("rank"):
                r["rank_chg"] = old_rank - r["rank"]
        state["snapshots"][idx["key"]] = {
            "date": today.isoformat(),
            "ranks": {r["code"]: r.get("rank") for r in rec.get("rows", []) if r.get("rank")},
        }
        out_indices.append(rec)
        log("index", idx["key"], "members", rec.get("member_count"), "rows", len(rec.get("rows", [])),
            "aum(조)", round(aum / 1e12, 1), "unmatched", len(unmatched))

    latest = {
        "sample": False,
        "asof": today.isoformat(),
        "generated_at": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "universe": len(universe),
        "calendar": CAL.upcoming(today),
        "indices": out_indices,
        "turnover_days": args.turnover_days,
    }
    save_json(os.path.join(DATA, "latest.json"), latest, compact=True)
    save_json(os.path.join(DATA, "state.json"), state, compact=True)
    status.update({"finished": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                   "minutes": round(elapsed_min(), 1), "universe": len(universe),
                   "universe_raw": len(raw_universe),
                   "unmatched": {i["key"]: i.get("unmatched") for i in out_indices if i.get("unmatched")},
                   "indices": len(out_indices),
                   "stale": [i["key"] for i in out_indices if i.get("stale")]})
    save_json(os.path.join(DATA, "status.json"), status)
    log("done:", json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
