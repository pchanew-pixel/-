"""매일 아침 경제·시사 키워드 뉴스 매거진을 생성해 Blogger에 자동 게시한다.

필요한 환경변수 (GitHub Secrets):
  공통: ANTHROPIC_API_KEY
  [간편] 이메일 게시: BLOGGER_POST_EMAIL, GMAIL_ADDRESS, GMAIL_APP_PASSWORD
  [고급] Blogger API: BLOGGER_BLOG_ID, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
  BLOGGER_POST_EMAIL 이 있으면 이메일 방식으로 게시한다.
MODE (워크플로 실행 시 선택):
  publish       : 글 생성 → 블로그 게시 (기본값, 매일 아침 자동 실행)
  preview       : 글 생성 → 블로그 대신 내 Gmail로 미리보기 발송 (게시 안 함)
  publish_saved : 미리보기로 만든 글(output.html, title.txt)을 그대로 블로그에 게시 (AI 비용 없음)
선택: DRY_RUN=1 이면 게시하지 않고 파일만 저장.
"""
import html
import os
import re
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
MAX_PER_FEED = 12


class KeywordItem(BaseModel):
    keyword: str          # 예: "기준금리"
    category: str         # "경제" 또는 "시사"
    headline: str         # 소제목 (핵심 키워드 포함)
    summary: str          # 자료에 근거한 2~4문장 요약
    why_it_matters: str   # 자료로 뒷받침되는 의미·영향 1문장. 근거가 없으면 빈 문자열
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
                desc = re.sub(r"<[^>]+>", " ", html.unescape(entry.get("summary", "")))
                desc = re.sub(r"\s+", " ", desc).strip()[:400]
                lines.append(f"[{n}번][{category}][{outlet}] {title}\n  내용: {desc}")
    if not lines:
        raise RuntimeError("수집된 뉴스가 없습니다. RSS 주소를 확인하세요.")
    return "\n".join(lines), sources


RULES = """[정확성 — 최우선]
- 오직 위 자료에 적힌 사실만 쓰세요. 자료에 없는 수치·날짜·인물 발언·정책·할인·이벤트·전망은 한 글자도 만들지 마세요.
- 자료가 제목뿐이거나 내용이 짧으면 요약도 짧게 쓰세요. 분량을 채우려고 추측하거나 일반론을 덧붙이지 마세요.
- why_it_matters 는 자료로 직접 뒷받침되는 의미나 영향이 있을 때만 한 문장으로 쓰고, 없으면 반드시 빈 문자열("")로 두세요.
  억지로 독자의 생활과 연결하지 마세요.
- 확정되지 않은 사안은 "~할 계획", "~를 검토 중"처럼 자료에 적힌 수준 그대로 표현하세요."""

STYLE = """[선별]
- 경제·사회·정치·국제 흐름에서 실제로 중요한 뉴스 5~8개를 고르세요(경제 비중을 더 크게).
  재난·안전 안내 문자, 행사·캠페인 홍보, 연예·스포츠, 단순 사건사고, 기업 홍보성 기사는 제외하세요.
- 같은 사건의 기사는 하나로 묶으세요. 개수를 채우려고 가벼운 뉴스를 넣지 마세요.

[문체 — 매거진형 기사]
- 경제 매거진 에디터의 문체: 정확하고 간결한 "~습니다/~입니다"체. 한 문장에 한 가지 정보.
- 구어체·감탄·개인 경험담("~더라고요", "~네요", "~죠", "출근길에 보니")은 쓰지 마세요.
- 상투어와 과장("주목할 만한", "귀추가 주목된다", "충격", "역대급", "알아보겠습니다", "여러분")은 쓰지 마세요.
- intro: 오늘 브리프의 핵심 흐름을 1~2문장으로 담담하게.
- closing: 자료에 근거해 오늘 뉴스의 공통 흐름을 정리하거나, 자료에 나온 향후 일정 하나를 짚는 1~2문장. 사견·덕담 금지."""


COST_LOG: list[float] = []
MODEL = "claude-sonnet-5-5"  # 비용 절감: Opus 대비 입력·출력 단가 절반


def _call(news: str, task: str) -> Magazine:
    """뉴스 자료+규칙(공통 앞부분)은 캐시해서, 두 번째 호출(팩트체크)에서 싸게 재사용한다."""
    client = anthropic.Anthropic()
    shared = f"""아래는 오늘 아침 수집한 한국 뉴스 자료입니다.

[자료]
{news}

{RULES}

{STYLE}"""
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "max"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": shared, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": task},
            ],
        }],
        output_format=Magazine,
    )
    u = response.usage
    cw, cr = u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0
    # Sonnet 5.5 단가(USD/100만 토큰): 입력 2, 캐시쓰기 2.5, 캐시읽기 0.1, 출력 10
    cost = (u.input_tokens * 2 + cw * 2.5 + cr * 0.1 + u.output_tokens * 10) / 1_000_000
    COST_LOG.append(cost)
    print(f"[usage] in={u.input_tokens} cache_write={cw} cache_read={cr} out={u.output_tokens} "
          f"→ ${cost:.4f}")
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"글 생성 실패: stop_reason={response.stop_reason}")
    return response.parsed_output


def write_magazine(news: str, today: str) -> Magazine:
    draft = _call(news, f"""오늘은 {today}입니다. 위 자료로 경제·시사 브리프 블로그 글을 작성하세요.

[구성]
- category: "경제" 또는 "시사" 둘 중 하나만.
- source_ids: 근거가 된 자료의 [N번] 숫자(1~3개). 모든 항목에 반드시 근거 자료가 있어야 합니다.
- title: 핵심 키워드 2~3개를 앞에 둔 40자 안팎의 담백한 제목. 날짜는 "11월 19일"처럼 짧게. 낚시성 표현 금지.
- headline: 해당 키워드를 포함한 사실 중심의 소제목.
- labels: 블로그 라벨 5개 안팎.""")

    # 2차 검수: 초안의 모든 문장을 자료와 대조해 근거 없는 내용을 지운다
    return _call(news, f"""당신은 경제 매거진의 팩트체크 담당 편집자입니다.
위 [자료]와 아래 [초안]을 문장 단위로 대조하세요.

[초안(JSON)]
{draft.model_dump_json()}

검수 기준:
- 각 항목의 summary·why_it_matters 문장이 그 항목 source_ids 자료에 실제로 적힌 내용인지 확인하세요.
  자료에 없는 사실·수치·할인·혜택·전망이 섞인 문장은 삭제하거나 자료 수준으로 고치세요.
- why_it_matters 가 자료로 뒷받침되지 않으면 빈 문자열("")로 바꾸세요.
- 중요도가 낮거나 선별 기준에 맞지 않는 항목(재난·안전 안내, 홍보, 연예 등)은 통째로 빼세요.
- 문체 기준에 어긋나는 표현은 고치세요.
- 새로운 사실을 추가하지 마세요. 결과는 같은 JSON 구조로 반환하세요.""")


# 상징색: 신뢰감을 주는 딥 네이비 + 옅은 틴트
BRAND, TINT, INK, SUB, LINE = "#1f3b73", "#f3f6fb", "#1a1a1a", "#8a8f99", "#e6e9ef"
FONT = ("font-family:'Pretendard','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;"
        f"color:{INK};font-size:17px;line-height:1.9;letter-spacing:-0.01em;word-break:keep-all")
LABEL = "font-size:12px;font-weight:700;letter-spacing:0.12em"
CAT_EN = {"경제": "ECONOMY", "시사": "ISSUE"}


def render_html(mag: Magazine, today: str, sources: dict[int, Source]) -> str:
    e = html.escape
    kw = lambda i: e(i.keyword.lstrip("#"))
    text_len = len(mag.intro + mag.closing + "".join(i.summary + i.why_it_matters for i in mag.items))
    minutes = max(2, round(text_len / 500))  # 한국어 분당 약 500자
    out = [f'<div style="{FONT};max-width:680px;margin:0 auto">']

    # 마스트헤드
    out.append(
        f'<div style="border-top:4px solid {BRAND};padding-top:14px;margin-bottom:22px">'
        f'<span style="{LABEL};color:{BRAND}">KEYWORD BRIEF</span>'
        f'<span style="{LABEL};color:{SUB};font-weight:500;letter-spacing:0.04em">'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;{e(today)}&nbsp;&nbsp;·&nbsp;&nbsp;읽는 시간 약 {minutes}분</span></div>'
    )
    # 인트로
    out.append(
        f'<p style="margin:0 0 32px;padding:18px 20px;background:{TINT};border-radius:12px;'
        f'font-size:18px;line-height:1.8">{e(mag.intro)}</p>'
    )
    # 목차
    rows, num = [], 0
    for cat in ("경제", "시사"):
        for i in (x for x in mag.items if x.category == cat):
            num += 1
            rows.append(
                f'<tr><td style="padding:7px 12px 7px 0;vertical-align:top;color:{BRAND};font-weight:800;'
                f'font-size:14px;white-space:nowrap">{num:02d}</td>'
                f'<td style="padding:7px 0;font-size:15px;line-height:1.6"><b>{kw(i)}</b>'
                f'<span style="color:{SUB}"> — {e(i.headline)}</span></td></tr>'
            )
    out.append(
        f'<div style="margin:0 0 48px;padding:18px 20px 12px;border:1px solid {LINE};border-radius:12px">'
        f'<p style="margin:0 0 8px;{LABEL};color:{BRAND}">IN THIS BRIEF</p>'
        f'<table style="border-collapse:collapse;width:100%">{"".join(rows)}</table></div>'
    )

    num = 0
    for cat in ("경제", "시사"):
        items = [i for i in mag.items if i.category == cat]
        if not items:
            continue
        out.append(
            f'<h2 style="margin:56px 0 30px;padding-bottom:10px;border-bottom:2px solid {BRAND};'
            f'font-size:22px;font-weight:800;color:{INK}">{cat}'
            f'<span style="{LABEL};color:{BRAND};margin-left:10px">{CAT_EN[cat]}</span></h2>'
        )
        for i in items:
            num += 1
            srcs = [sources[k] for k in dict.fromkeys(i.source_ids) if k in sources]
            links = "<br>".join(
                f'<a href="{e(s["url"])}" rel="noopener nofollow" style="color:{SUB};text-decoration:none">'
                f'<span style="color:{BRAND}">↗</span> {e(s["title"])} · {e(s["outlet"])}</a>'
                for s in srcs
            )
            out.append(
                f'<div style="margin:0 0 56px">'
                f'<p style="margin:0 0 4px;font-size:30px;font-weight:300;color:{BRAND};line-height:1.2">'
                f'{num:02d}</p>'
                f'<p style="margin:0 0 8px;font-size:14px;font-weight:700;color:{BRAND}">#{kw(i)}</p>'
                f'<h3 style="margin:0 0 16px;font-size:23px;font-weight:800;line-height:1.45;letter-spacing:-0.02em">'
                f'{e(i.headline)}</h3>'
                f'<p style="margin:0 0 18px">{e(i.summary)}</p>'
                + (
                    f'<div style="margin:0 0 16px;padding:14px 18px;background:{TINT};border-left:3px solid {BRAND};'
                    f'border-radius:0 10px 10px 0">'
                    f'<p style="margin:0 0 4px;{LABEL};color:{BRAND}">WHY IT MATTERS</p>'
                    f'<p style="margin:0">{e(i.why_it_matters)}</p></div>'
                    if i.why_it_matters.strip() else ""
                )
                + (f'<p style="margin:0;font-size:13px;line-height:1.9">{links}</p>' if links else "")
                + "</div>"
            )

    out.append(
        f'<div style="margin-top:56px;padding:22px 22px;background:{BRAND};border-radius:14px;color:#ffffff">'
        f'<p style="margin:0 0 8px;{LABEL};color:#b9c6e4">EDITOR’S NOTE</p>'
        f'<p style="margin:0;color:#ffffff">{e(mag.closing)}</p></div>'
        f'<p style="margin:20px 0 0;font-size:13px;color:{SUB};text-align:center">'
        f'매일 아침, 꼭 알아야 할 경제·시사 키워드를 정리합니다.</p>'
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


def publish_by_email(title: str, content: str, to_addr: str | None = None) -> str:
    """Blogger의 '이메일로 게시' 주소로 Gmail SMTP를 통해 글을 보낸다."""
    sender = os.environ["GMAIL_ADDRESS"].strip()
    preview = to_addr is not None
    to_addr = (to_addr or os.environ["BLOGGER_POST_EMAIL"]).strip()
    password = "".join(os.environ["GMAIL_APP_PASSWORD"].split())  # 공백·줄바꿈 제거

    # 값 형식 점검 (값 자체는 출력하지 않음)
    problems = []
    if not sender.lower().endswith("@gmail.com"):
        problems.append("GMAIL_ADDRESS 가 '...@gmail.com' 형식이 아닙니다.")
    if not preview and not to_addr.lower().endswith("@blogger.com"):
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


def post(title: str, content: str, labels: list[str]) -> None:
    if os.environ.get("BLOGGER_POST_EMAIL"):
        print("게시 완료:", publish_by_email(title, content))
    else:
        print("게시 완료:", publish(title, content, labels))


def main():
    mode = (os.environ.get("MODE") or "publish").strip()

    if mode == "publish_saved":  # 미리보기 글을 그대로 게시 (AI 호출 없음)
        with open("title.txt", encoding="utf-8") as f:
            title = f.read().strip()
        with open("output.html", encoding="utf-8") as f:
            content = f.read()
        post(title, content, [])
        return

    today = datetime.now(KST).strftime("%Y년 %m월 %d일")
    news, sources = collect_news()
    mag = write_magazine(news, today)
    # 근거 자료가 없는 항목은 버리고, 분류는 경제/시사로 정리
    mag.items = [i for i in mag.items if any(k in sources for k in i.source_ids)]
    for i in mag.items:
        if i.category not in ("경제", "시사"):
            i.category = "시사"
    if not mag.items:
        raise RuntimeError("근거가 확인된 뉴스 항목이 없어 게시를 중단합니다.")
    content = render_html(mag, today, sources)
    total = sum(COST_LOG)
    print(f"[cost] 오늘 AI 비용 합계: ${total:.4f} (약 {total * 1400:.0f}원, 환율 1,400원 가정)")

    # 게시가 실패해도 만든 글은 남도록 항상 파일로 저장 (Actions 결과의 output 파일)
    with open("output.html", "w", encoding="utf-8") as f:
        f.write(content)
    with open("title.txt", "w", encoding="utf-8") as f:
        f.write(mag.title)

    if os.environ.get("DRY_RUN") == "1":
        print("DRY_RUN: 파일 저장 완료")
    elif mode == "preview":
        me = os.environ["GMAIL_ADDRESS"]
        print("미리보기:", publish_by_email(f"[미리보기] {mag.title}", content, to_addr=me))
    else:
        post(mag.title, content, mag.labels)


if __name__ == "__main__":
    main()
