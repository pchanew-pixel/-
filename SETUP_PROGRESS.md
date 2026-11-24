# 설정 진행 상황 (2026-11-19 업데이트)

## 🔄 Claude Pro 구독으로 전환 (2026-11-24 준비)
- 코드 준비 완료: GitHub Secret `CLAUDE_CODE_OAUTH_TOKEN` 이 있으면 구독(Claude Code)으로 글 작성 → API 비용 0원
- 구독 단계가 실패하면 자동으로 기존 API(`ANTHROPIC_API_KEY`)로 작성 (크레딧 있을 때만)
- 남은 일: 내 PC에서 `claude setup-token` 으로 토큰 발급 → Secret `CLAUDE_CODE_OAUTH_TOKEN` 등록 → 미리보기 실행

## ✅ 최종 확정 설정 (2026-11-19, 사용자 승인)
- AI: Claude Sonnet 5.5, 생각 깊이 high — 글쓰기 + 2차 팩트체크 (자료 캐시 할인)
- 실측 비용: 1회 약 $0.13 (≈185원), 월 약 5,500원
- 원칙: 자료에 있는 사실만 / 근거 없으면 WHY IT MATTERS 생략 / 이름·직함은 자료 그대로 / 가벼운 뉴스 제외 / 5~8개
- 문체: 매거진형 기사체(~습니다), 구어체·상투어 금지
- 디자인: 딥 네이비(#1f3b73) 상징색, KEYWORD BRIEF 헤더, 읽는 시간, IN THIS BRIEF 목차, EDITOR'S NOTE
- 게시: 매일 07:07 KST 자동 (이메일 → Blogger)
- 수동 미리보기: Actions → Run workflow → mode=preview (내 Gmail로만 발송, 게시 안 함)

## 🎉 완료! (2026-11-19) 자동 게시 동작 확인
- 워크플로 켜짐(Enabled), 매일 07:07 KST 자동 게시
- 블로그 게시 주소 오류(Address not found)를 고친 뒤 블로그에 글이 올라온 것 확인
- 문제가 생기면: Claude에게 "SETUP_PROGRESS.md 보고 실패 원인 봐줘"
- Gmail에 "Mail Delivery Subsystem" 메일이 오면 → Blogger 설정의 이메일 게시 주소와 `BLOGGER_POST_EMAIL` 이 같은지 확인

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
