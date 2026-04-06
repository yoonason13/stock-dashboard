import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta

# Yahoo Finance 차단 우회 — curl_cffi로 Chrome TLS 핑거프린트 완전 위장
_yf_session = None
try:
    from curl_cffi import requests as curl_requests
    _yf_session = curl_requests.Session(impersonate="chrome120")
    print("[stock_service] curl_cffi 세션 사용 (Chrome 위장)")
except ImportError:
    # fallback: requests + User-Agent
    _yf_session = requests.Session()
    _yf_session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    })
    print("[stock_service] curl_cffi 없음 — requests 세션으로 대체")

# pykrx는 한국 주식에만 사용
try:
    from pykrx import stock as pykrx_stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False
    print("[stock_service] pykrx 미설치 — 한국 주식도 yfinance로 대체됩니다.")


def get_stock_data(ticker: str) -> dict | None:
    """티커가 .KS / .KQ 이면 pykrx, 아니면 yfinance로 조회합니다."""
    upper = ticker.upper()
    if PYKRX_AVAILABLE and (upper.endswith(".KS") or upper.endswith(".KQ")):
        return _get_korean_stock_data(ticker)
    return _get_us_stock_data(ticker)


# ── 한국 주식 (pykrx) ────────────────────────────────────────────────────────

def _last_trading_day() -> datetime:
    """가장 최근 거래일(평일)을 반환합니다."""
    d = datetime.now()
    while d.weekday() >= 5:  # 5=토요일, 6=일요일
        d -= timedelta(days=1)
    return d


def _get_korean_stock_data(ticker: str) -> dict | None:
    try:
        code = ticker.split(".")[0]  # "005930.KS" → "005930"

        # 날짜 범위 — todate는 반드시 거래일(평일)로
        last_td = _last_trading_day()
        start45 = (last_td - timedelta(days=60)).strftime("%Y%m%d")   # 거래일 30개 확보용
        start365 = (last_td - timedelta(days=380)).strftime("%Y%m%d")  # 52주 여유치
        todate = last_td.strftime("%Y%m%d")

        # 회사명
        company_name = pykrx_stock.get_market_ticker_name(code) or ticker

        # OHLCV (45일치 → 최근 30 거래일 차트용)
        ohlcv = pykrx_stock.get_market_ohlcv_by_date(start45, todate, code)
        if ohlcv is None or ohlcv.empty:
            return None

        current_price = float(ohlcv["종가"].iloc[-1])
        prev_close = float(ohlcv["종가"].iloc[-2]) if len(ohlcv) > 1 else current_price
        price_change = current_price - prev_close
        price_change_pct = (price_change / prev_close * 100) if prev_close else 0.0

        # 차트 (최근 30 거래일)
        chart_ohlcv = ohlcv.tail(30)
        chart_data = [
            {
                "date": d.strftime("%Y-%m-%d"),
                "close": int(row["종가"]),
                "volume": int(row["거래량"]),
            }
            for d, row in chart_ohlcv.iterrows()
        ]

        # 기술적 지표
        closes = ohlcv["종가"].astype(float)
        ma5 = _safe_float(closes.rolling(5).mean().iloc[-1]) if len(closes) >= 5 else None
        ma20 = _safe_float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else None
        rsi = _calculate_rsi(closes)

        price_30d_ago = chart_data[0]["close"] if chart_data else current_price
        change_30d = ((current_price - price_30d_ago) / price_30d_ago * 100) if price_30d_ago else 0.0

        # 펀더멘털 (pykrx) — PER, PBR, EPS, 배당수익률
        per = pbr = eps = dividend_yield = None
        try:
            fund_df = pykrx_stock.get_market_fundamental_by_date(start45, todate, code)
            if fund_df is not None and not fund_df.empty:
                f = fund_df.iloc[-1]
                per = _safe_float(f.get("PER")) or None   # 0이면 None 처리
                pbr = _safe_float(f.get("PBR")) or None
                eps = _safe_float(f.get("EPS")) or None
                div = _safe_float(f.get("DIV"))            # 이미 % 단위
                dividend_yield = div if div and div > 0 else None
        except Exception as e:
            print(f"[stock_service] {ticker} 펀더멘털 조회 실패: {e}")

        # 시가총액 (pykrx)
        market_cap = None
        try:
            cap_df = pykrx_stock.get_market_cap_by_date(start45, todate, code)
            if cap_df is not None and not cap_df.empty:
                market_cap = int(cap_df["시가총액"].iloc[-1])
        except Exception as e:
            print(f"[stock_service] {ticker} 시가총액 조회 실패: {e}")

        # 52주 고/저 (pykrx)
        fifty_two_week_high = fifty_two_week_low = None
        try:
            ohlcv_year = pykrx_stock.get_market_ohlcv_by_date(start365, todate, code)
            if ohlcv_year is not None and not ohlcv_year.empty:
                fifty_two_week_high = float(ohlcv_year["고가"].max())
                fifty_two_week_low = float(ohlcv_year["저가"].min())
        except Exception as e:
            print(f"[stock_service] {ticker} 52주 고저 조회 실패: {e}")

        # 추가 재무 정보 + 뉴스는 yfinance 보조 활용
        revenue = operating_income = roe = debt_to_equity = forward_per = None
        sector = industry = ""
        news = []
        try:
            yf_stock = yf.Ticker(ticker, session=_yf_session)
            yf_info = yf_stock.info or {}
            revenue = yf_info.get("totalRevenue")
            operating_income = yf_info.get("operatingIncome") or yf_info.get("ebitda")
            roe_raw = yf_info.get("returnOnEquity")
            roe = _safe_float(roe_raw)
            debt_to_equity = _safe_float(yf_info.get("debtToEquity"))
            forward_per = _safe_float(yf_info.get("forwardPE"))
            sector = yf_info.get("sector", "")
            industry = yf_info.get("industry", "")
            news = _get_news(yf_stock)
        except Exception as e:
            print(f"[stock_service] {ticker} yfinance 보조 조회 실패: {e}")

        return {
            "ticker": ticker,
            "company_name": company_name,
            "currency": "KRW",
            "current_price": current_price,
            "prev_close": prev_close,
            "price_change": round(price_change, 2),
            "price_change_pct": round(price_change_pct, 2),
            "change_30d": round(change_30d, 2),
            "market_cap": market_cap,
            "sector": sector,
            "industry": industry,
            "fifty_two_week_high": fifty_two_week_high,
            "fifty_two_week_low": fifty_two_week_low,
            "ma5": ma5,
            "ma20": ma20,
            "rsi": rsi,
            "per": per,
            "forward_per": forward_per,
            "pbr": pbr,
            "eps": eps,
            "dividend_yield": dividend_yield,
            "revenue": revenue,
            "operating_income": operating_income,
            "debt_to_equity": debt_to_equity,
            "roe": roe,
            "chart_data": chart_data,
            "news": news,
        }

    except Exception as e:
        print(f"[stock_service] {ticker} 한국 주식 조회 실패: {e}")
        return None


# ── 미국/기타 주식 (yfinance) ─────────────────────────────────────────────────

def _get_us_stock_data(ticker: str) -> dict | None:
    try:
        stock = yf.Ticker(ticker, session=_yf_session)

        # history 조회 — 30d 실패 시 3mo로 재시도
        hist = stock.history(period="30d")
        if hist.empty:
            hist = stock.history(period="3mo")
        if hist.empty:
            # 마지막 시도: yf.download 직접 호출
            hist = yf.download(ticker, period="30d", progress=False, session=_yf_session)
        if hist.empty:
            print(f"[stock_service] {ticker} history 데이터 없음")
            return None

        info = {}
        try:
            info = stock.info or {}
        except Exception as e:
            print(f"[stock_service] {ticker} info 조회 실패, history/fast_info로 계속 진행: {e}")

        fast_info = {}
        try:
            fast_info = dict(getattr(stock, "fast_info", {}) or {})
        except Exception as e:
            print(f"[stock_service] {ticker} fast_info 조회 실패: {e}")

        current_price = (
            fast_info.get("lastPrice")
            or fast_info.get("regularMarketPrice")
            or info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("navPrice")
        )

        if current_price is None:
            current_price = float(hist["Close"].iloc[-1])

        prev_close = (
            fast_info.get("previousClose")
            or info.get("previousClose")
            or info.get("regularMarketPreviousClose")
        )
        if prev_close is None:
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price

        current_price = float(current_price)
        prev_close = float(prev_close)
        price_change = current_price - prev_close
        price_change_pct = (price_change / prev_close * 100) if prev_close else 0.0

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

        dividend_yield_raw = info.get("dividendYield")
        dividend_yield = round(float(dividend_yield_raw) * 100, 2) if dividend_yield_raw else None

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
            "industry": info.get("industry", ""),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "ma5": ma5,
            "ma20": ma20,
            "rsi": rsi,
            "per": _safe_float(info.get("trailingPE")),
            "forward_per": _safe_float(info.get("forwardPE")),
            "pbr": _safe_float(info.get("priceToBook")),
            "eps": _safe_float(info.get("trailingEps")),
            "dividend_yield": dividend_yield,
            "revenue": info.get("totalRevenue"),
            "operating_income": info.get("operatingIncome") or info.get("ebitda"),
            "debt_to_equity": _safe_float(info.get("debtToEquity")),
            "roe": _safe_float(info.get("returnOnEquity")),
            "chart_data": chart_data,
            "news": news,
        }

    except Exception as e:
        print(f"[stock_service] {ticker} 미국 주식 조회 실패: {e}")
        return None


# ── 공통 유틸 ────────────────────────────────────────────────────────────────

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
    """yfinance 뉴스 파싱 (구버전/신버전 포맷 모두 지원)."""
    try:
        raw_news = stock.news or []
        result = []
        for item in raw_news[:6]:
            content = item.get("content", {})
            if content:
                title = content.get("title", "")
                link = (content.get("canonicalUrl") or {}).get("url", "")
                publisher = (content.get("provider") or {}).get("displayName", "")
                pub_date = content.get("pubDate", "")
            else:
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
