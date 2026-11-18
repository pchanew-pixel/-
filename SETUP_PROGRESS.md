# 설정 진행 상황 (2026-11-18 업데이트)

## 👉 다음에 여기서부터: ① 결제 → ② Enable workflow → ③ 실행 확인
현재 상태: 설정 전부 완료, 워크플로는 **꺼져 있음(Disabled)** — 사용자가 직접 끔.

1. **결제**: https://console.anthropic.com/settings/billing → 카드 등록 → 크레딧 $5 구매
2. **다시 켜기**: https://github.com/pchanew-pixel/-/actions/workflows/daily-news.yml
   → 위쪽 "This workflow was disabled" 옆 **Enable workflow** (없으면 오른쪽 위 ⋯ → Enable workflow)
3. **실행 확인**: 같은 화면 **Run workflow** → 초록 **Run workflow** → 2~3분 뒤 ✅ → 블로그 확인
   (❌ 이면 Claude에게 "SETUP_PROGRESS.md 보고 실패 원인 봐줘")

---

## 🎯 남은 일: 딱 1개 — Claude API 크레딧 충전

설정은 **전부 끝났습니다.** 첫 테스트 실행에서 뉴스 수집·API 키·Secret 모두 정상 확인됨.
실패 이유는 단 하나: `Your credit balance is too low` (크레딧 0원).

### 충전 방법
1. https://console.anthropic.com/settings/billing
2. 결제 수단(카드) 등록 → 크레딧 구매 **$5** (하루 약 $0.1~0.2 → 약 한 달)
3. (선택) 자동 충전(Auto-reload) 켜기 → 크레딧이 떨어져도 안 멈춤

### 충전 후
- **아무것도 안 해도** 다음 날 아침 07:07(KST)경 자동으로 글이 올라감
- 바로 확인하고 싶으면: https://github.com/pchanew-pixel/-/actions
  → Daily Keyword News → Run workflow → Run workflow
- ✅ 초록 체크 = 성공 / ❌ 빨간 X = Claude에게 "SETUP_PROGRESS.md 보고 실패 원인 봐줘"

## ⚠️ 충전 전까지
- 매일 아침 실행되고 실패하며, GitHub에서 실패 알림 메일이 올 수 있음 (무시해도 됨)
- 메일이 싫으면: https://github.com/pchanew-pixel/-/actions/workflows/daily-news.yml → 오른쪽 위 ⋯ → **Disable workflow**
  (이 경우 충전 후 같은 주소에서 **Enable workflow** 를 꼭 눌러야 함 — 실행 기록 화면 말고 이 주소!)

## ✅ 완료된 것
- 자동화 코드 (뉴스 수집 → Claude 요약 → 이메일로 Blogger 게시), 매일 07:07 KST 실행
- GitHub Secrets: `ANTHROPIC_API_KEY`, `BLOGGER_POST_EMAIL`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`
  (`BLOGGER_BLOG_ID` 도 있지만 이메일 방식에선 미사용)

## 💡 돈 안 들이는 대안 (원하면 Claude에게 요청)
- A. 구글 Gemini 무료 API로 요약 (Secret `GEMINI_API_KEY` 1개 추가)
- B. AI 없이 뉴스 제목 + 키워드 + 링크 목록만 게시 (완전 무료)

## 📌 기억할 것
- Claude API 키 만료일: 만들 때 고른 기간 확인 → 만료 전 새 키로 `ANTHROPIC_API_KEY` 교체
- Gmail 앱 비밀번호는 구글 비밀번호를 바꾸면 무효화됨 → 새로 발급해 `GMAIL_APP_PASSWORD` 교체
