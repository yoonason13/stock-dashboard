"""
News Sentiment & Investment Idea — 3-Agent Pipeline
  Agent 1 · News Fetcher     : yfinance + Tavily로 기사 수집
  Agent 2 · Sentiment Analyst: 기사별 감성 분류 + 요약
  Agent 3 · Idea Generator   : 투자 아이디어 리포트 작성
"""
import json
import os
import re
from datetime import datetime, timedelta

import requests
from anthropic import Anthropic

_client = None
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# 한국 주요 티커 → 회사명 매핑 (Tavily 검색 품질 향상)
KR_TICKER_MAP = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "005380": "현대차",
    "000270": "기아",
    "051910": "LG화학",
    "006400": "삼성SDI",
    "207940": "삼성바이오로직스",
    "068270": "셀트리온",
    "105560": "KB금융",
    "055550": "신한지주",
    "012330": "현대모비스",
    "028260": "삼성물산",
    "096770": "SK이노베이션",
    "034730": "SK",
    "017670": "SK텔레콤",
    "030200": "KT",
    "032830": "삼성생명",
    "066570": "LG전자",
}


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def _resolve_display_name(query: str) -> tuple[str, bool]:
    """
    티커 or 회사명을 받아서 (검색용 표시명, 한국주식여부) 반환.
    예) "000660.KS" → ("SK하이닉스", True)
        "AAPL"     → ("AAPL", False)
        "삼성전자"  → ("삼성전자", True)
    """
    q = query.strip()
    is_kr = q.upper().endswith(".KS") or q.upper().endswith(".KQ")

    if is_kr:
        code = q.split(".")[0]  # "000660"
        name = KR_TICKER_MAP.get(code)
        if not name:
            # yfinance로 회사명 조회 시도
            try:
                import yfinance as yf
                info = yf.Ticker(q).info
                name = info.get("longName") or info.get("shortName") or q
            except Exception:
                name = q
        return name, True

    return q, False


# ── Agent 1 Helper: yfinance 뉴스 ──────────────────────────────────────────

def _fetch_yfinance_news(ticker: str, days: int) -> list[dict]:
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        raw_news = stock.news or []
        cutoff = datetime.now() - timedelta(days=days)
        articles = []
        for n in raw_news[:20]:
            pub_ts = n.get("providerPublishTime", 0)
            pub_dt = datetime.fromtimestamp(pub_ts) if pub_ts else datetime.now()
            if pub_dt < cutoff:
                continue
            content_node = n.get("content") or {}
            title = content_node.get("title") or n.get("title", "")
            url   = (content_node.get("canonicalUrl", {}) or {}).get("url") or n.get("link", "")
            publisher = (content_node.get("provider", {}) or {}).get("displayName") or n.get("publisher", "")
            summary = content_node.get("summary") or ""
            if not title:
                continue
            articles.append({
                "title": title,
                "url": url,
                "source": publisher,
                "date": pub_dt.strftime("%Y-%m-%d"),
                "snippet": summary[:300] if summary else title,
            })
        return articles
    except Exception as e:
        print(f"[news_sentiment] yfinance error: {e}")
        return []


# ── Agent 1 Helper: Tavily 뉴스 ────────────────────────────────────────────

def _fetch_tavily_news(display_name: str, days: int, is_kr: bool) -> list[dict]:
    if not TAVILY_API_KEY:
        return []

    # 한국 주식이면 한국어 쿼리, 미국 주식이면 영어 쿼리
    if is_kr:
        queries = [
            f"{display_name} 주가 뉴스",
            f"{display_name} 실적 전망",
        ]
    else:
        queries = [
            f"{display_name} stock news",
            f"{display_name} earnings outlook",
        ]

    articles = []
    seen_titles = set()

    for query in queries:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "search_depth": "basic",
                    "topic": "news",
                    "days": days,
                    "max_results": 6,
                    "include_answer": False,
                },
                timeout=20,
            )
            results = resp.json().get("results", [])
            for r in results:
                title = r.get("title", "")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                domain = re.sub(r"https?://(www\.)?", "", r.get("url", "")).split("/")[0]
                articles.append({
                    "title": title,
                    "url": r.get("url", ""),
                    "source": domain,
                    "date": (r.get("published_date") or "")[:10] or datetime.now().strftime("%Y-%m-%d"),
                    "snippet": r.get("content", "")[:300],
                })
        except Exception as e:
            print(f"[news_sentiment] Tavily error ({query}): {e}")

    return articles


# ── JSON 파싱 헬퍼 ──────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        m2 = re.search(r"\{[\s\S]+\}", text)
        if m2:
            try:
                return json.loads(m2.group())
            except Exception:
                pass
    return {}


# ── 메인 파이프라인 ────────────────────────────────────────────────────────

def run_news_sentiment(query: str, days: int) -> dict:
    """
    3-Agent 뉴스 감성 분석 파이프라인

    Args:
        query : 티커(AAPL, 005930.KS) 또는 회사명
        days  : 분석 기간 (7 or 30)

    Returns:
        {news, sentiment, investment_idea, analyzed_at}
    """

    # ── Agent 1 · News Fetcher ────────────────────────────────────────────
    display_name, is_kr = _resolve_display_name(query)
    print(f"[Agent 1] '{query}' → 표시명: '{display_name}' | 기간: {days}일")

    articles: list[dict] = []

    # yfinance 시도 (티커처럼 생겼으면)
    looks_like_ticker = bool(re.match(r"^[A-Z0-9\.\-]{1,12}$", query.strip().upper()))
    if looks_like_ticker:
        articles = _fetch_yfinance_news(query.strip().upper(), days)
        print(f"[Agent 1] yfinance {len(articles)}건")

    # Tavily 보완
    if len(articles) < 5:
        extra = _fetch_tavily_news(display_name, days, is_kr)
        seen = {a["title"] for a in articles}
        for a in extra:
            if a["title"] and a["title"] not in seen:
                articles.append(a)
                seen.add(a["title"])
        print(f"[Agent 1] Tavily 보완 후 총 {len(articles)}건")

    articles = articles[:10]

    if not articles:
        return {"error": f"'{display_name}'에 대한 최근 뉴스를 찾을 수 없습니다. 다른 검색어를 시도해보세요."}

    print(f"[Agent 1] 최종 {len(articles)}개 기사")

    # 분석용 텍스트 구성
    news_text = "\n".join(
        f"{i+1}. [{a['date']}] {a['title']} | {a['source']}\n   {a['snippet']}"
        for i, a in enumerate(articles)
    )

    client = _get_client()

    # ── Agent 2 · Sentiment Analyst ───────────────────────────────────────
    print("[Agent 2] Analyzing sentiment...")

    sentiment_prompt = f"""You are a financial news sentiment analyst.

Analyze the following {len(articles)} news articles about **{display_name}** ({query}) from the past {days} days.

--- NEWS ---
{news_text}
---

Respond with ONLY valid JSON in this exact structure (no markdown, no explanation):
{{
  "articles": [
    {{"index": 1, "sentiment": "positive", "reason": "brief reason in Korean"}}
  ],
  "overall_sentiment": "positive",
  "positive_count": 0,
  "neutral_count": 0,
  "negative_count": 0,
  "key_themes": ["테마1", "테마2", "테마3"],
  "main_reasons": ["주요 이유1", "주요 이유2", "주요 이유3"]
}}

Rules:
- sentiment values must be exactly: "positive", "neutral", or "negative"
- overall_sentiment is the dominant sentiment
- key_themes are 2-3 recurring topics in Korean
- main_reasons explain why overall sentiment is what it is, in Korean
- all reasons/themes must be in Korean"""

    sentiment_data: dict = {}
    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": sentiment_prompt}],
        ) as stream:
            raw = stream.get_final_message().content[0].text
        sentiment_data = _parse_json(raw)
        print(f"[Agent 2] {sentiment_data.get('overall_sentiment')} "
              f"(+{sentiment_data.get('positive_count',0)} "
              f"~{sentiment_data.get('neutral_count',0)} "
              f"-{sentiment_data.get('negative_count',0)})")
    except Exception as e:
        print(f"[Agent 2] Error: {e}")
        sentiment_data = {
            "overall_sentiment": "neutral",
            "positive_count": 0,
            "neutral_count": len(articles),
            "negative_count": 0,
            "key_themes": [],
            "main_reasons": ["감성 분석 중 오류 발생"],
            "articles": [],
        }

    # ── Agent 3 · Investment Idea Generator ───────────────────────────────
    print("[Agent 3] Generating investment idea...")

    overall = sentiment_data.get("overall_sentiment", "neutral")
    pos = sentiment_data.get("positive_count", 0)
    neu = sentiment_data.get("neutral_count", 0)
    neg = sentiment_data.get("negative_count", 0)
    themes = ", ".join(sentiment_data.get("key_themes", []))
    reasons = "\n".join(f"- {r}" for r in sentiment_data.get("main_reasons", []))

    idea_prompt = f"""당신은 신한투자증권 리서치센터 시니어 애널리스트입니다.

종목/회사: {display_name} ({query})
분석 기간: 최근 {days}일
뉴스 감성 결과: {overall.upper()} (긍정 {pos}건 / 중립 {neu}건 / 부정 {neg}건)
주요 테마: {themes}
핵심 이유:
{reasons}

주요 뉴스 목록:
{news_text}

위 정보를 바탕으로 단기 투자 아이디어 리포트를 작성하세요.
반드시 아래 JSON 형식만 출력하세요 (마크다운 없이):
{{
  "core_conclusion": "핵심 결론 2~3문장 (한국어)",
  "bullish_points": ["강세 근거1", "강세 근거2", "강세 근거3"],
  "bearish_points": ["약세 리스크1", "약세 리스크2"],
  "watch_items": ["주목 포인트1", "주목 포인트2"],
  "recommendation": "매수 검토" 또는 "중립 관망" 또는 "리스크 주의"
}}"""

    investment_idea: dict = {}
    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": idea_prompt}],
        ) as stream:
            final_msg = stream.get_final_message()
        for block in final_msg.content:
            if block.type == "text":
                investment_idea = _parse_json(block.text)
                break
        print(f"[Agent 3] {investment_idea.get('recommendation')}")
    except Exception as e:
        print(f"[Agent 3] Error: {e}")
        investment_idea = {
            "core_conclusion": "투자 아이디어 생성 중 오류가 발생했습니다.",
            "bullish_points": [],
            "bearish_points": [],
            "watch_items": [],
            "recommendation": "중립 관망",
        }

    return {
        "query": query,
        "display_name": display_name,
        "period_days": days,
        "news": articles,
        "sentiment": sentiment_data,
        "investment_idea": investment_idea,
        "analyzed_at": datetime.now().isoformat(),
    }
