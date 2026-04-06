import json
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from services.claude_service import analyze_stock
from services.stock_service import get_stock_data

load_dotenv()

app = Flask(__name__)

WATCHLIST_FILE = os.path.join("data", "watchlist.json")
CACHE_DIR = os.path.join("data", "cache")


# ── 파일 헬퍼 ────────────────────────────────────────────────────────────────

def load_watchlist() -> list[str]:
    if not os.path.exists(WATCHLIST_FILE):
        return []
    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_watchlist(watchlist: list[str]) -> None:
    os.makedirs("data", exist_ok=True)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)


def load_cache(ticker: str) -> dict | None:
    path = os.path.join(CACHE_DIR, f"{ticker}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_cache(ticker: str, data: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{ticker}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_cache(ticker: str) -> None:
    path = os.path.join(CACHE_DIR, f"{ticker}.json")
    if os.path.exists(path):
        os.remove(path)


def build_full_data(ticker: str) -> dict | None:
    """주가 데이터 fetch + Claude 분석 → 캐시 저장 후 반환"""
    stock_data = get_stock_data(ticker)
    if not stock_data:
        return None
    analysis = analyze_stock(ticker, stock_data)
    full = {**stock_data, "analysis": analysis, "updated_at": datetime.now().isoformat()}
    save_cache(ticker, full)
    return full


# ── 라우트 ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    watchlist = load_watchlist()
    result = [{"ticker": t, "data": load_cache(t)} for t in watchlist]
    return jsonify(result)


@app.route("/api/watchlist", methods=["POST"])
def add_stock():
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "ticker가 필요합니다."}), 400

    watchlist = load_watchlist()
    if ticker in watchlist:
        return jsonify({"error": f"{ticker}는 이미 관심 종목에 있습니다."}), 400

    full_data = build_full_data(ticker)
    if not full_data:
        return jsonify({"error": f"유효하지 않은 티커입니다: {ticker}"}), 400

    watchlist.append(ticker)
    save_watchlist(watchlist)
    return jsonify({"ticker": ticker, "data": full_data}), 201


@app.route("/api/watchlist/<ticker>", methods=["DELETE"])
def remove_stock(ticker: str):
    ticker = ticker.upper()
    watchlist = load_watchlist()
    if ticker not in watchlist:
        return jsonify({"error": f"{ticker}는 관심 종목에 없습니다."}), 404

    watchlist.remove(ticker)
    save_watchlist(watchlist)
    delete_cache(ticker)
    return jsonify({"success": True})


@app.route("/api/refresh", methods=["POST"])
def refresh_all():
    watchlist = load_watchlist()
    results = []
    for ticker in watchlist:
        data = build_full_data(ticker)
        results.append({"ticker": ticker, "success": data is not None, "data": data})
    return jsonify(results)


@app.route("/api/refresh/<ticker>", methods=["POST"])
def refresh_one(ticker: str):
    ticker = ticker.upper()
    data = build_full_data(ticker)
    if not data:
        return jsonify({"error": f"{ticker} 데이터 갱신 실패"}), 500
    return jsonify({"ticker": ticker, "data": data})


# ── 스케줄러 ─────────────────────────────────────────────────────────────────

def daily_refresh_job():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 자동 갱신 시작...")
    for ticker in load_watchlist():
        try:
            build_full_data(ticker)
            print(f"  ✓ {ticker}")
        except Exception as e:
            print(f"  ✗ {ticker}: {e}")
    print("자동 갱신 완료.")


if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    # 평일 오전 9시 자동 갱신
    scheduler.add_job(daily_refresh_job, "cron", day_of_week="mon-fri", hour=9, minute=0)
    scheduler.start()

    try:
        app.run(debug=False, port=5000, use_reloader=False)
    finally:
        scheduler.shutdown()
