# 설정 진행 상황 (2026-11-18 기준)

## ✅ 완료
- [x] 자동화 코드 작성 및 업로드 (스크립트 + GitHub Actions, 매일 07:07 KST)
- [x] Claude API 키 발급 → GitHub Secret `ANTHROPIC_API_KEY` 등록
- [x] Google Cloud 프로젝트 `blogspot-daily-news` 생성
- [x] Blogger API v3 사용 설정
- [x] OAuth 브랜딩 정보 입력 (앱 이름, 지원 이메일, 개발자 연락처)
- [x] OAuth 클라이언트 생성 (클라이언트 ID 확인함)

## ⏳ 남은 일 (다음에 여기서부터)
1. [ ] **클라이언트 보안 비밀번호 받기**
   - https://console.cloud.google.com/auth/clients → `blogspot-daily-news` 클릭
   - 오른쪽 "클라이언트 보안 비밀번호" → **+ 보안 비밀번호 추가** → `GOCSPX-...` 복사
   - 그런 상자가 없으면 유형을 잘못 고른 것 → **웹 애플리케이션**으로 새로 만들기
     (리디렉션 URI: `https://developers.google.com/oauthplayground`)
2. [ ] GitHub Secrets 등록: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - https://github.com/pchanew-pixel/-/settings/secrets/actions/new
3. [ ] **앱 게시(프로덕션 전환)** — 지금 "테스트 중"이고 버튼이 회색
   - https://console.cloud.google.com/auth/audience → F5 → 앱 게시
   - 여전히 회색이면 브랜딩 페이지에 홈페이지/개인정보처리방침/서비스약관 = 블로그 주소,
     승인된 도메인 = `내블로그.blogspot.com` 입력 후 저장
   - ⚠️ 반드시 게시 후에 4번 진행 (테스트 상태 토큰은 7일 후 만료)
4. [ ] 리프레시 토큰 받기 (https://developers.google.com/oauthplayground)
   - ⚙️ → Use your own OAuth credentials → ID/비밀번호 입력
   - 스코프 `https://www.googleapis.com/auth/blogger` → Authorize APIs
   - 경고 화면은 고급 → 이동 → 허용 → Exchange authorization code for tokens
   - Refresh token → Secret `GOOGLE_REFRESH_TOKEN`
5. [ ] 블로그 ID → Secret `BLOGGER_BLOG_ID`
   - blogger.com 관리화면 주소 `.../blog/posts/숫자` 의 숫자
6. [ ] 테스트: https://github.com/pchanew-pixel/-/actions → Daily Keyword News → Run workflow

## 메모
- 이 저장소는 브랜치가 하나라 병합 없이 바로 스케줄 실행됨
- Claude API 키 만료일 확인 (30일로 만들었다면 12/18 전에 교체)
