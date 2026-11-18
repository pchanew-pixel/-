# 설정 진행 상황

## 방식 변경: 간편 "이메일 게시" 방식 (Google Cloud 설정 불필요)
Blogger의 '이메일로 게시' 기능을 사용한다. 필요한 Secret은 4개뿐.

| Secret | 상태 |
|---|---|
| `ANTHROPIC_API_KEY` | ❌ 등록 필요 (sk-ant-...) |
| `BLOGGER_POST_EMAIL` | ❌ Blogger 설정 → 이메일 → 이메일을 사용하여 게시 주소 |
| `GMAIL_ADDRESS` | ❌ 블로그 계정 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | ❌ https://myaccount.google.com/apppasswords 에서 발급한 16자리 |

- 앱 비밀번호 메뉴가 안 보이면 2단계 인증을 먼저 켜야 함: https://myaccount.google.com/signinoptions/twosv
- Blogger 이메일 게시 설정에서 **"이메일 즉시 게시"** 선택
- 등록 후: https://github.com/pchanew-pixel/-/actions → Daily Keyword News → Run workflow

## 참고
- 기존 Blogger API(OAuth) 방식 코드도 남아 있음. `BLOGGER_POST_EMAIL` 이 없으면 API 방식으로 동작.
- 이미 등록된 `BLOGGER_BLOG_ID` 는 이메일 방식에선 쓰지 않음 (지워도, 둬도 됨)
- 이메일 방식은 라벨 자동 지정이 안 됨
