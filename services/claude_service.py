import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def analyze_stock(ticker: str, stock_data: dict) -> str:
    """Claude API로 주식 종합 분석 리포트를 생성합니다."""
    client = _get_client()

    price = stock_data["current_price"]
    change = stock_data["price_change"]
    change_pct = stock_data["price_change_pct"]
    change_30d = stock_data.get("change_30d", 0)
    currency = stock_data["currency"]
    ma5 = stock_data.get("ma5")
    ma20 = stock_data.get("ma20")
    rsi = stock_data.get("rsi")
    company = stock_data["company_name"]
    sector = stock_data.get("sector", "N/A")
    high_52w = stock_data.get("fifty_two_week_high")
    low_52w = stock_data.get("fifty_two_week_low")

    # 뉴스 텍스트 구성
    news_lines = ""
    for i, n in enumerate(stock_data.get("news", []), 1):
        news_lines += f"{i}. {n['title']}"
        if n.get("publisher"):
            news_lines += f" ({n['publisher']})"
        news_lines += "\n"

    # MA 위치 판단
    ma_comment = ""
    if ma5 and ma20:
        if price > ma5 > ma20:
            ma_comment = "현재가가 MA5, MA20 모두 상회 (단기 강세)"
        elif price < ma5 < ma20:
            ma_comment = "현재가가 MA5, MA20 모두 하회 (단기 약세)"
        elif ma5 > ma20:
            ma_comment = "골든크로스 구간"
        else:
            ma_comment = "데드크로스 구간"

    # RSI 해석
    rsi_comment = ""
    if rsi:
        if rsi >= 70:
            rsi_comment = f"RSI {rsi:.1f} — 과매수 구간"
        elif rsi <= 30:
            rsi_comment = f"RSI {rsi:.1f} — 과매도 구간"
        else:
            rsi_comment = f"RSI {rsi:.1f} — 중립 구간"

    prompt = f"""다음 주식에 대한 종합 분석 리포트를 작성해주세요.

종목: {ticker} | 회사명: {company}
섹터: {sector}

━━━ 현재 주가 ━━━
현재가: {price:,.4f} {currency}
전일 대비: {change:+,.4f} {currency} ({change_pct:+.2f}%)
30일 수익률: {change_30d:+.2f}%
52주 최고: {f'{high_52w:,.4f} {currency}' if high_52w else 'N/A'}
52주 최저: {f'{low_52w:,.4f} {currency}' if low_52w else 'N/A'}

━━━ 기술적 지표 ━━━
MA5: {f'{ma5:,.4f} {currency}' if ma5 else 'N/A'}
MA20: {f'{ma20:,.4f} {currency}' if ma20 else 'N/A'}
{ma_comment}
{rsi_comment}

━━━ 최근 뉴스 ━━━
{news_lines if news_lines else '뉴스 없음'}

위 데이터를 분석하여 아래 형식으로 한국어 리포트를 작성해주세요.
각 섹션은 2~3문장으로 간결하게 작성하세요:

## 현황 요약
(현재 주가 동향 및 30일 추세 설명)

## 기술적 분석
(이동평균, RSI 등 기술적 지표 해석)

## 뉴스 영향 분석
(최근 뉴스가 주가에 미치는 영향 분석)

## 종합 의견
(단기 전망 및 주요 관심 포인트)

⚠️ 본 분석은 참고용이며 투자 권유가 아닙니다."""

    try:
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=1500,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            final_msg = stream.get_final_message()
            for block in final_msg.content:
                if block.type == "text":
                    return block.text
            return "분석 결과를 가져올 수 없습니다."
    except Exception as e:
        print(f"[claude_service] {ticker} 분석 실패: {e}")
        return f"분석 생성 중 오류 발생: {str(e)}"
