import yfinance as yf
import pandas as pd


def get_stock_data(ticker: str) -> dict | None:
    """yfinance로 주가 데이터, 기술적 지표, 뉴스를 가져옵니다."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # 유효한 티커인지 확인
        current_price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("navPrice")
        )

        hist = stock.history(period="30d")
        if hist.empty:
            return None

        if current_price is None:
            current_price = float(hist["Close"].iloc[-1])

        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        if prev_close is None:
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price

        current_price = float(current_price)
        prev_close = float(prev_close)
        price_change = current_price - prev_close
        price_change_pct = (price_change / prev_close * 100) if prev_close else 0.0

        # 30일 차트 데이터
        chart_data = [
            {
                "date": date.strftime("%Y-%m-%d"),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            }
            for date, row in hist.iterrows()
        ]

        closes = hist["Close"]
        ma5 = _safe_float(closes.rolling(5).mean().iloc[-1]) if len(closes) >= 5 else None
        ma20 = _safe_float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else None
        rsi = _calculate_rsi(closes)

        price_30d_ago = chart_data[0]["close"] if chart_data else current_price
        change_30d = ((current_price - price_30d_ago) / price_30d_ago * 100) if price_30d_ago else 0.0

        news = _get_news(stock)

        return {
            "ticker": ticker,
            "company_name": info.get("longName") or info.get("shortName") or ticker,
            "currency": info.get("currency", "USD"),
            "current_price": round(current_price, 4),
            "prev_close": round(prev_close, 4),
            "price_change": round(price_change, 4),
            "price_change_pct": round(price_change_pct, 2),
            "change_30d": round(change_30d, 2),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector", ""),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "ma5": ma5,
            "ma20": ma20,
            "rsi": rsi,
            "chart_data": chart_data,
            "news": news,
        }
    except Exception as e:
        print(f"[stock_service] {ticker} 데이터 조회 실패: {e}")
        return None


def _safe_float(value) -> float | None:
    try:
        v = float(value)
        return round(v, 4) if not pd.isna(v) else None
    except (TypeError, ValueError):
        return None


def _calculate_rsi(prices: pd.Series, period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    delta = prices.diff().dropna()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _get_news(stock) -> list[dict]:
    """yfinance의 뉴스를 파싱합니다 (구버전/신버전 포맷 모두 지원)."""
    try:
        raw_news = stock.news or []
        result = []
        for item in raw_news[:6]:
            # 신버전 포맷: item['content']
            content = item.get("content", {})
            if content:
                title = content.get("title", "")
                link = (content.get("canonicalUrl") or {}).get("url", "")
                publisher = (content.get("provider") or {}).get("displayName", "")
                pub_date = content.get("pubDate", "")
            else:
                # 구버전 포맷
                title = item.get("title", "")
                link = item.get("link", "")
                publisher = item.get("publisher", "")
                ts = item.get("providerPublishTime")
                pub_date = str(ts) if ts else ""

            if title:
                result.append(
                    {
                        "title": title,
                        "link": link,
                        "publisher": publisher,
                        "pub_date": pub_date,
                    }
                )
        return result
    except Exception as e:
        print(f"[stock_service] 뉴스 조회 실패: {e}")
        return []
