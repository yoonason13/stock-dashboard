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


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


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
            # yfinance v0.2 구조
            content_node = n.get("content") or {}
            title = content_node.get("title") or n.get("title", "")
            url   = (content_node.get("canonicalUrl", {}) or {}).get("url") or n.get("link", "")
            publisher = (content_node.get("provider", {}) or {}).get("displayName") or n.get("publisher", "")
            summary = content_node.get("summary") or ""
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

def _fetch_tavily_news(query: str, days: int) -> list[dict]:
    if not TAVILY_API_KEY:
        return []
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": f"{query} stock news analysis",
                "search_depth": "basic",
                "topic": "news",
                "days": days,
                "max_results": 8,
                "include_answer": False,
            },
            timeout=20,
        )
        results = resp.json().get("results", [])
        articles = []
        for r in results:
            domain = re.sub(r"https?://(www\.)?", "", r.get("url", "")).split("/")[0]
            articles.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "source": domain,
                "date": (r.get("published_date") or "")[:10] or datetime.now().strftime("%Y-%m-%d"),
                "snippet": r.get("content", "")[:300],
            })
        return articles
    except Exception as e:
        print(f"[news_sentiment] Tavily error: {e}")
        return []


# ── JSON 파싱 헬퍼 ──────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """Claude 응답에서 JSON을 안전하게 추출"""
    text = text.strip()
    # ``` 코드블록 제거
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        # 중괄호 범위만 추출 재시도
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
    print(f"[Agent 1] Fetching news for '{query}' (last {days}d)...")
    articles: list[dict] = []

    # yfinance 시도 (티커처럼 생겼으면)
    looks_like_ticker = bool(re.match(r"^[A-Z0-9\.\-]{1,12}$", query.strip().upper()))
    if looks_like_ticker:
        articles = _fetch_yfinance_news(query.strip().upper(), days)

    # Tavily 보완 (기사 부족하거나 회사명 검색)
    if len(articles) < 5:
        extra = _fetch_tavily_news(query, days)
        seen = {a["title"] for a in articles}
        for a in extra:
            if a["title"] and a["title"] not in seen:
                articles.append(a)
                seen.add(a["title"])

    articles = articles[:10]

    if not articles:
        return {"error": f"'{query}'에 대한 최근 뉴스를 찾을 수 없습니다."}

    print(f"[Agent 1] {len(articles)}개 기사 수집 완료")

    # 분석용 텍스트 구성
    news_text = "\n".join(
        f"{i+1}. [{a['date']}] {a['title']} | {a['source']}\n   {a['snippet']}"
        for i, a in enumerate(articles)
    )

    client = _get_client()

    # ── Agent 2 · Sentiment Analyst ───────────────────────────────────────
    print("[Agent 2] Analyzing sentiment...")

    sentiment_prompt = f"""You are a financial news sentiment analyst.

Analyze the following {len(articles)} news articles about **{query}** from the past {days} days.

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
        print(f"[Agent 2] Sentiment: {sentiment_data.get('overall_sentiment')} "
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

종목/회사: {query}
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
  "recommendation": "매수 검토" | "중립 관망" | "리스크 주의"
}}

Rules:
- core_conclusion: 뉴스 흐름 기반의 단기 투자 관점 요약
- bullish_points: 최소 2개, 최대 4개
- bearish_points: 최소 1개, 최대 3개
- watch_items: 향후 주목해야 할 이벤트/지표 2개
- recommendation: 세 값 중 하나만 정확히 사용"""

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
        print(f"[Agent 3] Recommendation: {investment_idea.get('recommendation')}")
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
        "period_days": days,
        "news": articles,
        "sentiment": sentiment_data,
        "investment_idea": investment_idea,
        "analyzed_at": datetime.now().isoformat(),
    }
