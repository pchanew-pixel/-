"""내 PC에서 딱 한 번 실행해 Google 리프레시 토큰을 발급받는 스크립트.

1) Google Cloud Console에서 OAuth 클라이언트(데스크톱 앱)를 만들고 JSON을 client_secret.json 으로 저장
2) pip install google-auth-oauthlib
3) python get_refresh_token.py  → 브라우저 로그인 → 출력된 값을 GitHub Secrets에 등록
"""
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json", scopes=["https://www.googleapis.com/auth/blogger"]
)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("GOOGLE_CLIENT_ID     =", creds.client_id)
print("GOOGLE_CLIENT_SECRET =", creds.client_secret)
print("GOOGLE_REFRESH_TOKEN =", creds.refresh_token)
