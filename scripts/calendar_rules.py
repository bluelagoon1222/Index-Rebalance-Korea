# -*- coding: utf-8 -*-
"""
Index review calendar.

All dates are computed from published methodology rules, not scraped, so they are marked as
estimates where a public holiday could shift them by a day. Sources are noted per family.

Rules encoded
  KRX 정기변경 (KOSPI 200 / KOSDAQ 150)
    - 연 2회, 6월·12월. 변경일은 해당 월 선물·옵션 만기일(둘째 목요일)의 다음 거래일.
    - 심사기준: 직전 기간의 일평균 시가총액(유동시총) 순위와 산업군별 누적시총 85%,
      최소 상장기간 6개월.
  FnGuide 섹터 TOP10 계열 (반도체 TOP10 등)
    - 선정기준일: 3월·9월 마지막 영업일. 변경일: 4월·10월 선물·옵션 만기일 다음 주 첫 영업일.
    - 비중 확정: 변경일 2영업일 전 종가. 상위 2종목 각 25%, 나머지 8종목이 50%를 유동시총 가중.
      특정 종목 비중이 30%를 넘으면 조정.
  MSCI 분기 리뷰
    - 2·5·8·11월. 5월·11월은 반기 리뷰(SAIR)로 변경 폭이 큼. 리밸런싱은 해당 월 마지막 영업일 종가.
  FTSE GEIS 반기·분기 리뷰
    - 3·6·9·12월. 리밸런싱은 셋째 금요일 종가 기준.
"""
import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))

# 2026-2027 한국 증시 휴장일 (확정된 공휴일 기준. 임시 휴장은 반영되지 않음)
HOLIDAYS = {
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-01", "2026-03-02",
    "2026-05-01", "2026-05-05", "2026-05-24", "2026-05-25", "2026-06-03", "2026-06-06",
    "2026-08-15", "2026-08-17", "2026-09-24", "2026-09-25", "2026-09-26", "2026-10-03",
    "2026-10-05", "2026-10-09", "2026-12-25", "2026-12-31",
    "2027-01-01", "2027-02-05", "2027-02-06", "2027-02-07", "2027-03-01", "2027-05-01",
    "2027-05-05", "2027-05-13", "2027-06-06", "2027-08-15", "2027-09-14", "2027-09-15",
    "2027-09-16", "2027-10-03", "2027-10-09", "2027-12-25", "2027-12-31",
}


def is_bday(d):
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def next_bday(d):
    d += dt.timedelta(days=1)
    while not is_bday(d):
        d += dt.timedelta(days=1)
    return d


def prev_bday(d):
    d -= dt.timedelta(days=1)
    while not is_bday(d):
        d -= dt.timedelta(days=1)
    return d


def add_bdays(d, n):
    for _ in range(abs(n)):
        d = next_bday(d) if n > 0 else prev_bday(d)
    return d


def nth_weekday(year, month, weekday, n):
    """n-th given weekday of a month (weekday: Mon=0 .. Sun=6)."""
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(days=7 * (n - 1))


def last_bday_of_month(year, month):
    d = dt.date(year + (month == 12), (month % 12) + 1, 1) - dt.timedelta(days=1)
    return d if is_bday(d) else prev_bday(d)


def expiry(year, month):
    """선물·옵션 만기일 = 둘째 목요일 (휴장이면 전 영업일)."""
    d = nth_weekday(year, month, 3, 2)
    return d if is_bday(d) else prev_bday(d)


def krx_regular(year, month):
    """KOSPI200 / KOSDAQ150 정기변경 일정."""
    ex = expiry(year, month)
    eff = next_bday(ex)
    return {
        "review": "%d년 %d월 정기변경" % (year, month),
        "cutoff": last_bday_of_month(year, month - 2).isoformat(),
        "cutoff_label": "심사 기준기간 종료(통상 변경 2개월 전 말)",
        "announce": add_bdays(eff, -12).isoformat(),
        "announce_label": "거래소 발표(통상 변경 3주 전)",
        "effective": eff.isoformat(),
        "effective_label": "구성종목 변경(만기 다음 거래일)",
        "estimated": True,
    }


def fnguide_sector(year, month):
    """FnGuide 섹터 TOP10 계열 정기변경 (4월·10월)."""
    ex = expiry(year, month)
    eff = ex + dt.timedelta(days=(7 - ex.weekday()))  # 만기일 다음 주 월요일
    if not is_bday(eff):
        eff = next_bday(eff)
    sel = last_bday_of_month(year, 3 if month == 4 else 9)  # 선정기준일: 3월 또는 9월 말
    return {
        "review": "%d년 %d월 정기변경" % (year, month),
        "cutoff": sel.isoformat(),
        "cutoff_label": "종목 선정기준일(3·9월 말 영업일)",
        "announce": add_bdays(eff, -5).isoformat(),
        "announce_label": "비중 확정(변경일 2영업일 전 종가)·사전 공지",
        "effective": eff.isoformat(),
        "effective_label": "변경 적용(만기 다음 주 첫 영업일)",
        "estimated": True,
    }


def msci_review(year, month):
    eff = last_bday_of_month(year, month)
    semi = month in (5, 11)
    return {
        "review": "%d년 %d월 %s" % (year, month, "반기 리뷰(SAIR)" if semi else "분기 리뷰(QIR)"),
        "cutoff": add_bdays(eff, -25).isoformat(),
        "cutoff_label": "가격 기준일(리뷰 월 초 무작위 영업일)",
        "announce": nth_weekday(year, month, 1, 2).isoformat(),
        "announce_label": "MSCI 발표(통상 둘째 주)",
        "effective": eff.isoformat(),
        "effective_label": "리밸런싱(월말 종가)",
        "estimated": True,
    }


def ftse_review(year, month):
    eff = nth_weekday(year, month, 4, 3)  # 셋째 금요일
    if not is_bday(eff):
        eff = prev_bday(eff)
    return {
        "review": "%d년 %d월 리뷰" % (year, month),
        "cutoff": last_bday_of_month(year, month - 1).isoformat(),
        "cutoff_label": "기준일(직전월 말)",
        "announce": add_bdays(eff, -10).isoformat(),
        "announce_label": "FTSE 발표",
        "effective": eff.isoformat(),
        "effective_label": "리밸런싱(셋째 금요일 종가)",
        "estimated": True,
    }


FAMILIES = [
    {"key": "krx_regular", "name": "KOSPI 200 · KOSDAQ 150 정기변경", "months": (6, 12),
     "fn": krx_regular, "source": "한국거래소 지수 산출 기준 (연 2회, 6·12월)",
     "note": "심사: 산업군별 누적 유동시총 85%, 최소 상장 6개월. 변경일은 만기 다음 거래일."},
    {"key": "fnguide_sector", "name": "FnGuide 섹터 TOP10 (반도체 등)", "months": (4, 10),
     "fn": fnguide_sector, "source": "FnGuide 지수 방법론 (연 2회, 4·10월)",
     "note": "상위 2종목 각 25%, 나머지 8종목이 50%를 유동시총 가중. 30% 초과 시 조정."},
    {"key": "msci", "name": "MSCI 지수 리뷰", "months": (2, 5, 8, 11),
     "fn": msci_review, "source": "MSCI Index Review 일정 (분기, 5·11월 반기)",
     "note": "편입·편출 후보는 본 사이트에서 산출하지 않습니다. 일정 확인용입니다."},
    {"key": "ftse", "name": "FTSE GEIS 리뷰", "months": (3, 6, 9, 12),
     "fn": ftse_review, "source": "FTSE Russell 리뷰 일정 (분기)",
     "note": "편입·편출 후보는 본 사이트에서 산출하지 않습니다. 일정 확인용입니다."},
]


def upcoming(today=None, horizon_days=400):
    """Next review of every family, sorted by effective date."""
    today = today or dt.datetime.now(KST).date()
    out = []
    for fam in FAMILIES:
        for year in (today.year, today.year + 1):
            for month in fam["months"]:
                ev = fam["fn"](year, month)
                eff = dt.date.fromisoformat(ev["effective"])
                if eff < today or (eff - today).days > horizon_days:
                    continue
                ev.update({"family": fam["key"], "family_name": fam["name"], "source": fam["source"],
                           "note": fam["note"],
                           "d_effective": (eff - today).days,
                           "d_announce": (dt.date.fromisoformat(ev["announce"]) - today).days,
                           "d_cutoff": (dt.date.fromisoformat(ev["cutoff"]) - today).days})
                out.append(ev)
    out.sort(key=lambda e: e["effective"])
    return out


if __name__ == "__main__":
    import json
    for e in upcoming():
        print(json.dumps(e, ensure_ascii=False))
