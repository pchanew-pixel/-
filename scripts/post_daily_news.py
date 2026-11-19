"""매일 아침 경제·시사 키워드 뉴스 매거진을 생성해 Blogger에 자동 게시한다.

필요한 환경변수 (GitHub Secrets):
  공통: ANTHROPIC_API_KEY
  [간편] 이메일 게시: BLOGGER_POST_EMAIL, GMAIL_ADDRESS, GMAIL_APP_PASSWORD
  [고급] Blogger API: BLOGGER_BLOG_ID, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
  BLOGGER_POST_EMAIL 이 있으면 이메일 방식으로 게시한다.
선택: DRY_RUN=1 이면 게시하지 않고 HTML만 output.html 로 저장.
"""
import html
import os
import smtplib
import sys
from email.header import Header
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

import anthropic
import feedparser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel

KST = timezone(timedelta(hours=9))

# 필요하면 원하는 언론사 RSS를 추가/교체하세요.
FEEDS = {
    "경제": [
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
        "https://www.yna.co.kr/rss/economy.xml",
        "https://www.hankyung.com/feed/economy",
    ],
    "시사": [
        "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko",
        "https://www.yna.co.kr/rss/politics.xml",
        "https://www.yna.co.kr/rss/international.xml",
    ],
}
MAX_PER_FEED = 15


class KeywordItem(BaseModel):
    keyword: str          # 예: "#기준금리"
    category: str         # "경제" 또는 "시사"
    headline: str         # 한 줄 제목
    summary: str          # 2~3문장 핵심 요약 (자체 문장)
    why_it_matters: str   # 왜 중요한가 1문장
    source_urls: list[str]


class Magazine(BaseModel):
    title: str
    intro: str
    items: list[KeywordItem]
    closing: str
    labels: list[str]


def collect_news() -> str:
    lines, seen = [], set()
    for category, urls in FEEDS.items():
        for url in urls:
            try:
                feed = feedparser.parse(url)
            except Exception as e:  # 피드 하나가 실패해도 계속 진행
                print(f"[warn] {url}: {e}", file=sys.stderr)
                continue
            for entry in feed.entries[:MAX_PER_FEED]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                desc = html.unescape(entry.get("summary", ""))[:300]
                lines.append(f"[{category}] {title}\n  링크: {entry.get('link', '')}\n  내용: {desc}")
    if not lines:
        raise RuntimeError("수집된 뉴스가 없습니다. RSS 주소를 확인하세요.")
    return "\n".join(lines)


def write_magazine(news: str, today: str) -> Magazine:
    client = anthropic.Anthropic()
    prompt = f"""오늘은 {today}입니다. 아래는 오늘 아침 수집한 한국 경제·시사 뉴스 헤드라인입니다.

{news}

이 자료로 '오늘의 키워드 뉴스 매거진' 블로그 글을 만들어 주세요.
- 가장 중요한 키워드 8~10개를 고르고(경제 5~6, 시사 3~4), 같은 사건의 중복 기사는 하나로 묶으세요.
- 기사 문장을 그대로 옮기지 말고 당신의 문장으로 핵심만 요약하세요(저작권).
- 자료에 없는 사실·수치는 지어내지 마세요.
- source_urls에는 위 자료의 링크만 넣으세요.
- title은 날짜를 포함한 매력적인 제목, labels는 블로그 라벨 5개 내외."""

    response = client.beta.messages.parse(
        model="claude-opus-5-5",
        max_tokens=16000,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
        output_format=Magazine,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"글 생성 실패: stop_reason={response.stop_reason}")
    return response.parsed_output


def render_html(mag: Magazine, today: str) -> str:
    e = html.escape
    parts = [
        f'<p style="color:#888">📅 {e(today)} · 오늘의 키워드 뉴스</p>',
        f"<p>{e(mag.intro)}</p>",
    ]
    for cat in ("경제", "시사"):
        items = [i for i in mag.items if i.category == cat]
        if not items:
            continue
        parts.append(f"<h2>{'💰' if cat == '경제' else '🗞️'} {cat}</h2>")
        for i in items:
            links = " · ".join(
                f'<a href="{e(u)}" target="_blank" rel="noopener">출처{n}</a>'
                for n, u in enumerate(i.source_urls, 1)
            )
            parts.append(
                f'<h3><span style="color:#2a6df4">{e(i.keyword)}</span> {e(i.headline)}</h3>'
                f"<p>{e(i.summary)}</p>"
                f"<p>👉 <b>왜 중요한가:</b> {e(i.why_it_matters)}</p>"
                f'<p style="font-size:0.85em">{links}</p>'
            )
    parts.append(f"<hr><p>{e(mag.closing)}</p>")
    parts.append('<p style="font-size:0.8em;color:#888">※ 이 글은 공개 뉴스를 바탕으로 AI가 요약했습니다. 정확한 내용은 원문을 확인하세요.</p>')
    return "\n".join(parts)


def publish(title: str, content: str, labels: list[str]) -> str:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/blogger"],
    )
    service = build("blogger", "v3", credentials=creds, cache_discovery=False)
    post = service.posts().insert(
        blogId=os.environ["BLOGGER_BLOG_ID"],
        body={"title": title, "content": content, "labels": labels},
        isDraft=os.environ.get("POST_AS_DRAFT") == "1",
    ).execute()
    return post.get("url", post.get("id"))


def publish_by_email(title: str, content: str) -> str:
    """Blogger의 '이메일로 게시' 주소로 Gmail SMTP를 통해 글을 보낸다."""
    sender = os.environ["GMAIL_ADDRESS"].strip()
    to_addr = os.environ["BLOGGER_POST_EMAIL"].strip()
    password = "".join(os.environ["GMAIL_APP_PASSWORD"].split())  # 공백·줄바꿈 제거

    # 값 형식 점검 (값 자체는 출력하지 않음)
    problems = []
    if not sender.lower().endswith("@gmail.com"):
        problems.append("GMAIL_ADDRESS 가 '...@gmail.com' 형식이 아닙니다.")
    if not to_addr.lower().endswith("@blogger.com"):
        problems.append("BLOGGER_POST_EMAIL 이 '...@blogger.com' 형식이 아닙니다.")
    if len(password) != 16 or not password.isascii() or not password.isalpha():
        problems.append(
            f"GMAIL_APP_PASSWORD 는 영문 16글자여야 하는데, 지금은 {len(password)}글자입니다. "
            "https://myaccount.google.com/apppasswords 에서 새로 발급해 다시 등록하세요."
        )
    if problems:
        raise RuntimeError("Secret 값 확인 필요:\n- " + "\n- ".join(problems))

    msg = MIMEText(content, "html", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = sender
    msg["To"] = to_addr

    def send(smtp):
        smtp.login(sender, password)
        smtp.send_message(msg)

    try:
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as smtp:
                send(smtp)
        except (smtplib.SMTPServerDisconnected, OSError) as e:
            if isinstance(e, smtplib.SMTPAuthenticationError):
                raise
            print(f"[info] 465 포트 실패({type(e).__name__}), 587 포트로 재시도")
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as smtp:
                smtp.starttls()
                send(smtp)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(
            "Gmail 로그인 거절: GMAIL_ADDRESS 와 GMAIL_APP_PASSWORD 가 같은 구글 계정 것인지, "
            "앱 비밀번호가 맞는지 확인하세요. "
            f"(서버 응답 코드 {e.smtp_code})"
        ) from None
    return "이메일 게시 요청 전송 (블로그에 1~2분 내 반영)"


def main():
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")
    mag = write_magazine(collect_news(), today)
    content = render_html(mag, today)
    # 게시가 실패해도 만든 글은 남도록 항상 파일로 저장 (Actions 결과의 output 파일)
    with open("output.html", "w", encoding="utf-8") as f:
        f.write(f"<h1>{html.escape(mag.title)}</h1>\n{content}")
    if os.environ.get("DRY_RUN") == "1":
        print("DRY_RUN: output.html 저장 완료")
        return
    if os.environ.get("BLOGGER_POST_EMAIL"):
        print("게시 완료:", publish_by_email(mag.title, content))
    else:
        print("게시 완료:", publish(mag.title, content, mag.labels))


if __name__ == "__main__":
    main()
