"""매일 아침 경제·시사 키워드 뉴스 매거진을 생성해 Blogger에 자동 게시한다.

필요한 환경변수 (GitHub Secrets):
  ANTHROPIC_API_KEY, BLOGGER_BLOG_ID,
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
선택: DRY_RUN=1 이면 게시하지 않고 HTML만 output.html 로 저장.
"""
import html
import os
import sys
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


def main():
    today = datetime.now(KST).strftime("%Y년 %m월 %d일")
    mag = write_magazine(collect_news(), today)
    content = render_html(mag, today)
    if os.environ.get("DRY_RUN") == "1":
        with open("output.html", "w", encoding="utf-8") as f:
            f.write(f"<h1>{html.escape(mag.title)}</h1>\n{content}")
        print("DRY_RUN: output.html 저장 완료")
        return
    print("게시 완료:", publish(mag.title, content, mag.labels))


if __name__ == "__main__":
    main()
