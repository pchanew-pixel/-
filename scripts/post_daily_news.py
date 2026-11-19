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

[문체 — 가장 중요]
- 매일 아침 경제 뉴스를 챙겨 읽는 30대 직장인 블로거가 이웃에게 이야기하듯 쓰세요.
  딱딱한 보고서나 보도자료 말투가 아니라, 읽는 사람이 고개를 끄덕일 만한 생활 감각이 묻어나는 존댓말.
- 항목마다 같은 틀을 반복하지 마세요. 어떤 건 배경부터, 어떤 건 숫자부터, 어떤 건 질문으로 시작하는 식으로
  도입을 바꾸고, 문단 길이도 내용 무게에 따라 다르게 하세요(중요한 건 길게, 가벼운 건 짧게).
- 다음 표현은 쓰지 마세요: "~에 대해 알아보겠습니다", "~를 살펴보겠습니다", "결론적으로", "요약하자면",
  "다양한", "중요한 역할", "주목할 만한", "시사하는 바가 크다", "귀추가 주목된다", "~할 것으로 보입니다"의 반복,
  "여러분", 과도한 느낌표와 이모지.
- "~습니다"만 연달아 쓰지 말고 "~죠", "~더라고요", "~네요" 같은 어미를 적당히 섞되 과하지 않게.
- why_it_matters 는 제목 없이 그대로 읽혀도 자연스러운 한두 문장으로, "그래서 내 월급·대출·투자·장바구니에
  무슨 의미인지"를 구체적으로. 매번 같은 말로 시작하지 마세요.
- intro 는 오늘 아침 분위기를 한 줄로 잡고 핵심 키워드로 자연스럽게 이어지게.
  closing 은 교훈조나 "좋은 하루 되세요" 같은 인사 대신, 오늘 뉴스를 보고 든 짧은 생각이나
  앞으로 지켜볼 일정 하나로 담백하게 마무리.

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


INK, SUB, LINE, POINT = "#111111", "#8c8c8c", "#e9e9e9", "#ff4f00"
FONT = ("font-family:'Pretendard','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;"
        f"color:{INK};font-size:17px;line-height:1.9;letter-spacing:-0.01em;word-break:keep-all")
LABEL = f"font-size:12px;font-weight:700;letter-spacing:0.14em;color:{SUB};text-transform:uppercase"
CAT_EN = {"경제": "ECONOMY", "시사": "ISSUE"}


def render_html(mag: Magazine, today: str, sources: dict[int, Source]) -> str:
    e = html.escape
    kw = lambda i: e(i.keyword.lstrip("#"))
    out = [f'<div style="{FONT};max-width:680px;margin:0 auto">']

    # 상단
    out.append(
        f'<p style="margin:0 0 20px;{LABEL}">Morning Brief — {e(today)}</p>'
        f'<p style="margin:0 0 28px;font-size:19px;line-height:1.75;font-weight:500">{e(mag.intro)}</p>'
    )
    # 키워드 한 줄
    out.append(
        f'<p style="margin:0 0 48px;padding:16px 0;border-top:1px solid {INK};border-bottom:1px solid {LINE};'
        f'font-size:15px;line-height:1.9"><b style="margin-right:10px">TODAY</b>'
        + f'<span style="color:{SUB}"> / </span>'.join(kw(i) for i in mag.items)
        + "</p>"
    )

    num = 0
    for cat in ("경제", "시사"):
        items = [i for i in mag.items if i.category == cat]
        if not items:
            continue
        out.append(
            f'<h2 style="margin:56px 0 28px;font-size:13px;font-weight:800;letter-spacing:0.18em;color:{INK}">'
            f'{CAT_EN[cat]}<span style="color:{SUB};font-weight:500;letter-spacing:0"> · {cat}</span></h2>'
        )
        for i in items:
            num += 1
            srcs = [sources[k] for k in dict.fromkeys(i.source_ids) if k in sources]
            links = "<br>".join(
                f'<a href="{e(s["url"])}" rel="noopener nofollow" style="color:{SUB};text-decoration:none;'
                f'border-bottom:1px solid {LINE}">{e(s["outlet"])} ↗ {e(s["title"])}</a>'
                for s in srcs
            )
            out.append(
                f'<div style="margin:0 0 52px">'
                f'<p style="margin:0 0 6px;font-size:13px;font-weight:700;color:{POINT}">'
                f'{num:02d}<span style="color:{SUB};font-weight:500">&nbsp;&nbsp;#{kw(i)}</span></p>'
                f'<h3 style="margin:0 0 16px;font-size:24px;font-weight:800;line-height:1.4;letter-spacing:-0.02em">'
                f'{e(i.headline)}</h3>'
                f'<p style="margin:0 0 16px">{e(i.summary)}</p>'
                f'<p style="margin:0 0 16px;padding-left:14px;border-left:2px solid {POINT};font-weight:600">'
                f'{e(i.why_it_matters)}</p>'
                + (f'<p style="margin:0;font-size:13px;line-height:1.8">{links}</p>' if links else "")
                + "</div>"
            )

    out.append(
        f'<div style="margin-top:64px;padding-top:24px;border-top:1px solid {INK}">'
        f'<p style="margin:0 0 10px;{LABEL}">Editor’s Note</p>'
        f'<p style="margin:0">{e(mag.closing)}</p></div>'
        "</div>"
    )
    return "\n".join(out)


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
