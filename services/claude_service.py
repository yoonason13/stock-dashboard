import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None

# ── System Prompt ─────────────────────────────────────────────────────────────
ANALYST_SYSTEM_PROMPT = """당신은 신한투자증권 리서치센터의 시니어 주식 애널리스트입니다.

## 역할과 전문성
- 국내외 주식 시장에 대한 깊은 이해를 보유
- 기술적 분석(차트, 이동평균, RSI, MACD 등)과 기본적 분석(PER, PBR, EPS, 재무제표 등)을 모두 활용
- 거시경제 환경(금리, 환율, 인플레이션)이 주식 시장에 미치는 영향 분석
- 한국 주식(KOSPI/KOSDAQ)과 미국 주식(NYSE/NASDAQ) 모두 커버

## 응답 원칙
1. **객관성**: 데이터와 근거에 기반한 분석 제공
2. **명확성**: 전문 용어는 간단히 설명하여 이해하기 쉽게 전달
3. **균형성**: 긍정적 요인과 리스크 요인을 균형있게 제시
4. **실용성**: 투자자가 실제 의사결정에 활용할 수 있는 인사이트 제공
5. **면책**: 모든 분석은 참고용이며 투자 권유가 아님을 명시

## 응답 형식
- 한국어로 답변
- 핵심 내용을 먼저 제시 후 상세 설명
- 수치와 근거를 구체적으로 인용
- 필요 시 bullet point와 섹션 헤더 활용"""


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
            model="claude-sonnet-4-6",
            max_tokens=1500,
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


def analyze_query(question: str, context: dict | None = None) -> dict:
    """
    /analyze 엔드포인트용 범용 분석 함수.

    Args:
        question: 사용자 질문 (자유 형식)
        context: 선택적 추가 컨텍스트 (ticker, price 등)

    Returns:
        {"answer": str, "thinking": str | None, "input_tokens": int, "output_tokens": int}
    """
    client = _get_client()

    # 컨텍스트가 있으면 질문에 첨부
    user_content = question
    if context:
        ctx_lines = "\n".join(f"- {k}: {v}" for k, v in context.items() if v is not None)
        if ctx_lines:
            user_content = f"{question}\n\n### 참고 컨텍스트\n{ctx_lines}"

    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=ANALYST_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            final_msg = stream.get_final_message()

        answer = ""
        for block in final_msg.content:
            if block.type == "text":
                answer = block.text

        return {
            "answer": answer or "분석 결과를 가져올 수 없습니다.",
            "thinking": None,
            "input_tokens": final_msg.usage.input_tokens,
            "output_tokens": final_msg.usage.output_tokens,
        }

    except anthropic.BadRequestError as e:
        print(f"[claude_service] analyze_query BadRequest: {e}")
        return {"answer": f"요청 오류: {e.message}", "thinking": None,
                "input_tokens": 0, "output_tokens": 0}
    except anthropic.RateLimitError:
        return {"answer": "API 호출 한도 초과입니다. 잠시 후 다시 시도해주세요.",
                "thinking": None, "input_tokens": 0, "output_tokens": 0}
    except Exception as e:
        print(f"[claude_service] analyze_query 실패: {e}")
        return {"answer": f"분석 생성 중 오류 발생: {str(e)}", "thinking": None,
                "input_tokens": 0, "output_tokens": 0}
