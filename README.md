# 📰 오늘의 키워드 뉴스 — Blogger 자동 게시

매일 아침 07:07(KST)에 GitHub Actions가 자동으로:
1. 경제·시사 RSS(구글뉴스, 연합뉴스, 한국경제)에서 헤드라인 수집
2. Claude API로 키워드 8~10개를 골라 핵심 요약 매거진 작성
3. Blogger API로 구글 블로그스팟에 게시

PC를 켜 둘 필요가 없습니다. 아래 준비는 **처음 한 번만** 하면 됩니다.

## 1단계. Claude API 키
- https://console.anthropic.com → API Keys → 키 발급 (결제수단 등록 필요)

## 2단계. Blogger 블로그 ID
- Blogger 관리 화면 주소 `https://www.blogger.com/blog/posts/1234567890123456789`의 숫자

## 3단계. Google OAuth 리프레시 토큰
1. https://console.cloud.google.com → 새 프로젝트
2. "API 및 서비스 → 라이브러리"에서 **Blogger API v3** 사용 설정
3. "OAuth 동의 화면" 구성 → 외부 → 테스트 사용자에 내 Gmail 추가 → **앱 게시(프로덕션)** 로 전환
   (테스트 상태로 두면 토큰이 7일 후 만료됩니다)
4. "사용자 인증 정보 → OAuth 클라이언트 ID → 데스크톱 앱" 생성 → JSON 다운로드 → `client_secret.json`으로 저장
5. 내 PC에서:
   ```bash
   pip install google-auth-oauthlib
   python scripts/get_refresh_token.py
   ```
   출력된 3개 값을 복사

## 4단계. GitHub Secrets 등록
저장소 → Settings → Secrets and variables → Actions → New repository secret

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | 1단계 키 |
| `BLOGGER_BLOG_ID` | 2단계 숫자 |
| `GOOGLE_CLIENT_ID` | 3단계 출력 |
| `GOOGLE_CLIENT_SECRET` | 3단계 출력 |
| `GOOGLE_REFRESH_TOKEN` | 3단계 출력 |

## 5단계. 테스트 & 가동
- 이 워크플로가 **기본 브랜치(main)** 에 있어야 스케줄이 동작합니다.
- Actions 탭 → "Daily Keyword News" → **Run workflow** 로 즉시 테스트
- 이후 매일 아침 자동 실행

## 커스터마이즈
- 시간: `.github/workflows/daily-news.yml`의 cron (UTC 기준, KST-9시간)
- 언론사: `scripts/post_daily_news.py`의 `FEEDS`
- 문체/키워드 수: 같은 파일의 `prompt`
- 임시저장으로 먼저 검토하고 싶으면 워크플로 env에 `POST_AS_DRAFT: "1"` 추가

## 참고/주의
- 비용: 하루 1회 기준 Claude API 약 몇십 원~백 원대 (기사량에 따라 변동), GitHub Actions 무료
- GitHub 스케줄은 수 분~수십 분 지연될 수 있습니다
- 저장소에 60일간 커밋이 없으면 GitHub가 스케줄을 자동 중지할 수 있으니 가끔 확인하세요
- 기사 원문 복제 대신 자체 요약 + 출처 링크 방식으로 저작권 위험을 줄였습니다
