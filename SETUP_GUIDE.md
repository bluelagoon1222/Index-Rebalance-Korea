# 지수 정기변경 CHECK — 설치 안내 (5단계, 약 15분)

Finviz-Korea·액티브 ETF CHECK·자사주 CHECK와 같은 방식입니다.
**이번에는 DART 인증키가 필요하지 않습니다.** 네이버 금융과 WiseReport만 쓰기 때문입니다.

> 압축 파일 안의 파일은 메모장으로 열어 저장하지 마세요(한글이 깨집니다). 그대로 업로드만 하시면 됩니다.

---

## 1단계. 새 저장소 만들기

1. 링크 열기: https://github.com/new
2. **Repository name** 에 입력:
   ```
   Index-Rebalance-Korea
   ```
3. **Public** 선택 (사이트 공개에 필수)
4. 다른 체크박스는 건드리지 말고 맨 아래 초록색 **Create repository** 클릭

---

## 2단계. 파일 업로드 (숨김 폴더 주의)

1. 받으신 `Index-Rebalance-Korea.zip` 을 압축 해제합니다.
2. 링크 열기: https://github.com/bluelagoon1222/Index-Rebalance-Korea/upload/main
3. 압축 해제한 폴더 **안의 파일과 폴더 전부(Ctrl+A)** 를 브라우저 업로드 영역에 끌어다 놓습니다.
4. 초록색 **Commit changes** 클릭

업로드가 끝나면 저장소 첫 화면에 `.github` 폴더가 보이는지 확인해 주세요.
자사주 CHECK 때처럼 **점(.)으로 시작하는 폴더가 빠지는 경우가 있습니다.** 안 보이면 3단계로,
보이면 3단계를 건너뛰고 4단계로 가시면 됩니다.

---

## 3단계. (`.github` 가 안 보일 때만) 자동 실행 파일 직접 만들기

1. 링크 열기: https://github.com/bluelagoon1222/Index-Rebalance-Korea/new/main?filename=.github/workflows/update.yml
2. 압축 해제한 폴더의 `.github/workflows/update.yml` 을 메모장이 아닌 **브라우저나 VS Code로 열어**
   내용 전체를 복사해 본문 칸에 붙여 넣습니다. (영문 파일이라 그대로 붙여도 안전합니다)
3. 오른쪽 위 초록색 **Commit changes…** → 다시 **Commit changes**

---

## 4단계. 자동 수집 권한 + 공개 사이트 켜기

1. 링크 열기: https://github.com/bluelagoon1222/Index-Rebalance-Korea/settings/actions
   화면 **맨 아래** **Workflow permissions** 에서 **Read and write permissions** 선택 → **Save**
2. 링크 열기: https://github.com/bluelagoon1222/Index-Rebalance-Korea/settings/pages
   **Source** = `Deploy from a branch`, **Branch** = `main` / `/ (root)` → **Save**
3. 1~2분 후 아래 주소로 사이트가 열립니다. 처음에는 노란색 "샘플 데이터" 띠가 보이는 것이 정상입니다.
   ```
   https://bluelagoon1222.github.io/Index-Rebalance-Korea/
   ```

---

## 5단계. 첫 수집 실행

1. 링크 열기: https://github.com/bluelagoon1222/Index-Rebalance-Korea/actions/workflows/update.yml
2. 오른쪽 **Run workflow** → 다시 초록색 **Run workflow** (칸은 그대로)
3. **5~15분**이면 끝납니다. 자사주 트래커와 달리 과거 이력을 쌓지 않아 매번 짧습니다.
   - **초록 체크**: 성공. 사이트를 새로고침하면 샘플 띠가 사라집니다.
   - **빨간 X**: 실패. 실행 항목 → `update` → **Collect index and market data** 단계를 펼쳐
     마지막 20줄 정도를 복사해 주세요. 바로 수정본을 드리겠습니다.

이후에는 평일 **08:20 · 18:40(KST)** 에 자동 갱신됩니다.

---

## 자주 묻는 것

- **다른 지수도 추가할 수 있나요?** 네. `scripts/indices.py` 에 지수 이름, 대표 ETF 코드, 추종자금
  집계용 이름 패턴만 넣으면 탭이 하나 늘어납니다. 원하시는 지수를 말씀해 주시면 설정된 파일을 드리겠습니다.
- **추종자금 숫자가 실제와 다른 것 같은데요?** 상장 ETF 순자산만 자동 집계한 값이라 인덱스펀드·연금은
  빠져 있습니다. 화면의 **추종자금 가정** 입력칸에 원하는 값을 넣으면 모든 금액이 즉시 다시 계산됩니다.
  그 값은 브라우저에 저장되지 않으므로 새로고침하면 자동 집계값으로 돌아갑니다.
- **왜 편입 후보가 실제 발표와 다를 수 있나요?** 거래소는 유동시가총액과 산업군별 누적시총 85%,
  최소 상장 6개월 요건을 함께 봅니다. 이 사이트는 공개 데이터로 얻을 수 있는 전체 시가총액 순위로
  근사한 것이어서, 경계에 걸린 종목은 결과가 갈릴 수 있습니다. 화면의 "경계 대비" 칸이 그 여유를 보여줍니다.
- **10월 반도체TOP10 정기변경 준비는 어떻게 하나요?** 캘린더의 FnGuide 카드에서 D-day를 확인하고,
  **FnGuide 반도체 TOP10** 탭에서 삼성전자·SK하이닉스의 목표 비중 되돌림 금액과 거래대금 대비 일수를
  보시면 됩니다. 선정기준일(9월 30일) 종가가 확정되면 그날 저녁 갱신분이 가장 정확합니다.
