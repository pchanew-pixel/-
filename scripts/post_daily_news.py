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
    keyword: str          # 예: "기준금리"
    category: str         # "경제" 또는 "시사"
    headline: str         # 소제목 (핵심 키워드 포함)
    summary: str          # 3~4문장 요약 + 배경 설명 (자체 문장)
    why_it_matters: str   # 독자 생활·투자에 미치는 영향 1~2문장
    source_ids: list[int] # 자료의 [N번] 번호


class Magazine(BaseModel):
    title: str            # SEO 제목 (이메일 제목 = 블로그 글 제목)
    intro: str
    items: list[KeywordItem]
    closing: str
    labels: list[str]


Source = dict  # {"outlet": 언론사, "title": 기사 제목, "url": 링크}


def collect_news() -> tuple[str, dict[int, Source]]:
    """뉴스를 모아 번호를 붙인다. 출처 링크는 이 번호로만 연결해 가짜 링크를 막는다."""
    lines, seen, sources = [], set(), {}
    for category, urls in FEEDS.items():
        for url in urls:
            try:
                feed = feedparser.parse(url)
            except Exception as e:  # 피드 하나가 실패해도 계속 진행
                print(f"[warn] {url}: {e}", file=sys.stderr)
                continue
            feed_name = feed.feed.get("title", "")
            for entry in feed.entries[:MAX_PER_FEED]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link.startswith("http") or title in seen:
                    continue
                seen.add(title)
                outlet = (entry.get("source") or {}).get("title") or feed_name
                # 구글뉴스 제목은 "기사 제목 - 언론사" 형태라 언론사 부분을 떼어낸다
                if outlet and title.endswith(f" - {outlet}"):
                    title = title[: -len(f" - {outlet}")]
                outlet = outlet.split(":")[0].split("|")[0].strip() or "원문"
                n = len(sources) + 1
                sources[n] = {"outlet": outlet, "title": title, "url": link}
                desc = html.unescape(entry.get("summary", ""))[:300]
                lines.append(f"[{n}번][{category}][{outlet}] {title}\n  내용: {desc}")
    if not lines:
        raise RuntimeError("수집된 뉴스가 없습니다. RSS 주소를 확인하세요.")
    return "\n".join(lines), sources


def write_magazine(news: str, today: str) -> Magazine:
    client = anthropic.Anthropic()
    prompt = f"""오늘은 {today}입니다. 아래는 오늘 아침 수집한 한국 경제·시사 뉴스입니다.

{news}

이 자료로 경제·시사 블로그의 '오늘의 키워드 뉴스' 글을 써 주세요.

[내용]
- 가장 중요한 키워드 8~10개를 고르세요(경제 5~6, 시사 3~4). 같은 사건의 기사는 하나로 묶으세요.
- 기사 문장을 옮기지 말고 직접 소화한 문장으로 쓰세요. 단순 요약을 넘어 배경과 맥락을 한두 문장 덧붙여,
  기사를 여러 개 읽지 않아도 흐름이 이해되게 하세요.
- 자료에 없는 사실·수치·인용은 절대 만들지 마세요. 확실하지 않은 전망은 단정하지 마세요.
- source_ids 에는 근거가 된 자료의 [N번] 숫자만 넣으세요(1~3개).

[문체]
- 경제 뉴스를 꾸준히 챙겨 보는 블로거가 독자에게 설명하듯, 자연스럽고 읽기 쉬운 존댓말로 쓰세요.
- 문장 길이와 시작을 다양하게 하고, "~에 대해 알아보겠습니다", "결론적으로", "다양한", "중요한 역할" 같은
  상투적인 표현과 과장된 수식어는 피하세요. 같은 어미를 연달아 반복하지 마세요.
- why_it_matters 는 "그래서 내 지갑·투자·생활에 무슨 의미인지"를 구체적으로 쓰세요.

[검색 노출(SEO)]
- title: 가장 큰 핵심 키워드 2~3개를 앞쪽에 넣은 40자 안팎의 제목. 날짜는 "11월 19일"처럼 짧게 넣고,
  낚시성·자극적인 표현은 쓰지 마세요.
- headline: 각 키워드가 포함된, 검색어처럼 구체적인 소제목.
- intro: 2~3문장. 오늘의 핵심 키워드 몇 개가 자연스럽게 들어가게.
- labels: 블로그 라벨 5개 안팎(예: 경제뉴스, 오늘의뉴스, 핵심 키워드)."""

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


H2 = ("font-size:1.6em;font-weight:800;color:#111;margin:1.6em 0 0.6em;"
      "padding:0.3em 0 0.3em 0.6em;border-left:6px solid #2a6df4;line-height:1.35")
H3 = "font-size:1.3em;font-weight:800;color:#111;margin:1.4em 0 0.5em;line-height:1.4"


def render_html(mag: Magazine, today: str, sources: dict[int, Source]) -> str:
    e = html.escape
    parts = [
        f'<p style="color:#666;font-size:0.95em">📅 {e(today)} · 오늘의 키워드 뉴스</p>',
        f'<div style="background:#f4f7ff;border-radius:10px;padding:1em 1.2em;margin:1em 0;'
        f'font-size:1.05em;line-height:1.7">{e(mag.intro)}</div>',
    ]
    # 목차
    toc = "".join(f"<li><b>{e(i.keyword)}</b> — {e(i.headline)}</li>" for i in mag.items)
    parts.append(f'<p style="font-weight:700;margin-bottom:0.3em">📌 오늘의 키워드</p><ol>{toc}</ol>')

    for cat in ("경제", "시사"):
        items = [i for i in mag.items if i.category == cat]
        if not items:
            continue
        parts.append(f'<h2 style="{H2}">{"💰" if cat == "경제" else "🗞️"} {cat} 뉴스</h2>')
        for i in items:
            srcs = [sources[n] for n in dict.fromkeys(i.source_ids) if n in sources]
            links = "".join(
                f'<li><a href="{e(s["url"])}" rel="noopener nofollow">'
                f'{e(s["outlet"])} | {e(s["title"])}</a></li>'
                for s in srcs
            )
            parts.append(
                f'<h3 style="{H3}"><span style="color:#2a6df4">#{e(i.keyword.lstrip("#"))}</span> '
                f"{e(i.headline)}</h3>"
                f'<p style="line-height:1.8">{e(i.summary)}</p>'
                f'<p style="line-height:1.8">👉 <b>왜 중요할까?</b> {e(i.why_it_matters)}</p>'
            )
            if links:
                parts.append(
                    f'<p style="font-size:0.9em;color:#555;margin-bottom:0.2em">📰 관련 기사</p>'
                    f'<ul style="font-size:0.9em">{links}</ul>'
                )
    parts.append(f'<hr><p style="line-height:1.8">{e(mag.closing)}</p>')
    parts.append(
        '<p style="font-size:0.8em;color:#888">※ 공개된 언론 보도를 바탕으로 AI 도구의 도움을 받아 정리했습니다. '
        "정확한 내용은 위 관련 기사 원문을 확인해 주세요.</p>"
    )
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
    news, sources = collect_news()
    mag = write_magazine(news, today)
    content = render_html(mag, today, sources)
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
