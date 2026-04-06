import sys
import io
import json
import os
import locale
import builtins
import traceback
from datetime import datetime

# ── UTF-8 전역 패치 (Render ASCII 환경 완전 우회) ────────────────────────────
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
os.environ["LANG"] = "C.UTF-8"
os.environ["LC_ALL"] = "C.UTF-8"

# locale 강제 설정
for _lc in ("C.UTF-8", "en_US.UTF-8", "C"):
    try:
        locale.setlocale(locale.LC_ALL, _lc)
        break
    except Exception:
        pass

# stdout/stderr 재설정
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

# print() 전역 패치 — 모든 서비스 파일 print()에 적용됨
_orig_print = builtins.print
def _safe_print(*args, **kwargs):
    try:
        _orig_print(*args, **kwargs)
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            safe = tuple(str(a).encode("utf-8", "replace").decode("ascii", "replace") for a in args)
            _orig_print(*safe, **kwargs)
        except Exception:
            pass
builtins.print = _safe_print

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from services.claude_service import analyze_stock
from services.stock_service import get_stock_data

load_dotenv()

app = Flask(__name__)

# API 경로는 모든 에러를 JSON으로 반환
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    return e

@app.errorhandler(500)
def internal_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": f"서버 내부 오류: {str(e)}"}), 500
    return e

WATCHLIST_FILE = os.path.join("data", "watchlist.json")
CACHE_DIR = os.path.join("data", "cache")
RESEARCH_CACHE_DIR = os.path.join("data", "research_cache")
RESEARCH_HISTORY_FILE = os.path.join("data", "research_history.json")


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


# ── 리서치 캐시 헬퍼 ─────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)


def load_research_cache(company: str) -> dict | None:
    path = os.path.join(RESEARCH_CACHE_DIR, f"{_safe_filename(company)}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_research_cache(company: str, data: dict) -> None:
    os.makedirs(RESEARCH_CACHE_DIR, exist_ok=True)
    path = os.path.join(RESEARCH_CACHE_DIR, f"{_safe_filename(company)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_research_history() -> list[dict]:
    if not os.path.exists(RESEARCH_HISTORY_FILE):
        return []
    with open(RESEARCH_HISTORY_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_research_history(history: list[dict]) -> None:
    os.makedirs("data", exist_ok=True)
    with open(RESEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


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


# ── 진단 엔드포인트 ──────────────────────────────────────────────────────────

@app.route("/api/diag", methods=["GET"])
def diag():
    """API 키 및 외부 서비스 연결 진단"""
    results = {}

    # 0. API 키 앞 10자 확인 (진단용)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    results["api_key_preview"] = repr(api_key[:15]) if api_key else "NOT SET"

    # 1. 어느 헤더가 한글인지 찾기
    bad_header_values = []
    try:
        import httpx._models as _hm
        _orig_norm = _hm._normalize_header_value
        def _debug_norm(value, encoding=None):
            try:
                return _orig_norm(value, encoding)
            except UnicodeEncodeError:
                bad_header_values.append(repr(value[:80]))
                raise
        _hm._normalize_header_value = _debug_norm
    except Exception as patch_err:
        results["patch_err"] = str(patch_err)

    try:
        import anthropic
        c = anthropic.Anthropic(api_key=api_key)
        msg = c.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK"}],
        )
        results["anthropic"] = "ok: " + (msg.content[0].text if msg.content else "no content")
    except Exception as e:
        results["anthropic"] = "error: " + traceback.format_exc()[-300:]
        results["bad_header"] = bad_header_values  # 문제 헤더 값
    finally:
        try:
            import httpx._models as _hm2
            _hm2._normalize_header_value = _orig_norm
        except Exception:
            pass

    # 1b. requests로 직접 호출 테스트 (httpx 우회)
    try:
        import requests as req
        raw = req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": "claude-sonnet-4-6", "max_tokens": 10,
                  "messages": [{"role": "user", "content": "Say OK"}]},
            timeout=30,
        )
        results["anthropic_raw_requests"] = f"status={raw.status_code} body={raw.text[:150]}"
    except Exception as e:
        results["anthropic_raw_requests"] = f"error: {e}"

    # 2. Tavily API 테스트
    try:
        import requests as req
        r = req.post(
            "https://api.tavily.com/search",
            json={"api_key": os.environ.get("TAVILY_API_KEY", ""), "query": "test", "max_results": 1},
            timeout=10,
        )
        results["tavily"] = f"ok (status {r.status_code})" if r.status_code == 200 else f"error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        results["tavily"] = f"error: {str(e)[:200]}"

    # 3. 환경변수 및 인코딩 상태
    results["ANTHROPIC_API_KEY_set"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    results["TAVILY_API_KEY_set"] = bool(os.environ.get("TAVILY_API_KEY"))
    results["stdout_encoding"] = getattr(sys.stdout, "encoding", "unknown")
    results["PYTHONUTF8"] = os.environ.get("PYTHONUTF8", "not set")
    results["PYTHONIOENCODING"] = os.environ.get("PYTHONIOENCODING", "not set")
    results["LANG"] = os.environ.get("LANG", "not set")
    results["LC_ALL"] = os.environ.get("LC_ALL", "not set")
    results["locale_preferred"] = locale.getpreferredencoding(False)
    results["fs_encoding"] = sys.getfilesystemencoding()
    results["default_encoding"] = sys.getdefaultencoding()

    return jsonify(results)


# ── /analyze 엔드포인트 ──────────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    범용 Claude 분석 에이전트 엔드포인트.

    Request body (JSON):
        question  (str, required) : 분석 질문
        context   (dict, optional): 추가 컨텍스트 (ticker, price 등)

    Response (JSON):
        answer        (str)      : Claude 분석 답변
        thinking      (str|null) : 내부 추론 과정 (adaptive thinking)
        input_tokens  (int)      : 소비된 입력 토큰 수
        output_tokens (int)      : 소비된 출력 토큰 수
    """
    body = request.get_json(silent=True) or {}
    question = body.get("question", "").strip()
    context = body.get("context") or None

    if not question:
        return jsonify({"error": "question 필드가 필요합니다."}), 400
    if len(question) > 4000:
        return jsonify({"error": "질문이 너무 깁니다 (최대 4000자)."}), 400

    from services.claude_service import analyze_query
    result = analyze_query(question, context)
    return jsonify(result)


# ── FDD 라우트 ───────────────────────────────────────────────────────────────

FDD_CACHE_DIR = os.path.join("data", "fdd_cache")

ALLOWED_EXTENSIONS = {"pdf", "xlsx", "xls", "xlsm"}
MAX_FILE_MB = 20


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXTENSIONS


@app.route("/api/fdd/upload", methods=["POST"])
def fdd_upload():
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "파일명이 없습니다."}), 400
    if not _allowed_file(f.filename):
        return jsonify({"error": "PDF, Excel(.xlsx/.xls) 파일만 업로드 가능합니다."}), 400

    file_bytes = f.read()
    if len(file_bytes) > MAX_FILE_MB * 1024 * 1024:
        return jsonify({"error": f"파일 크기가 {MAX_FILE_MB}MB를 초과합니다."}), 400

    company_name = request.form.get("company_name", "").strip()

    from services.fdd_service import run_fdd
    result = run_fdd(file_bytes, f.filename, company_name)

    if "error" in result:
        return jsonify(result), 400

    result["analyzed_at"] = datetime.now().isoformat()

    # 캐시 저장
    os.makedirs(FDD_CACHE_DIR, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (company_name or f.filename))
    cache_path = os.path.join(FDD_CACHE_DIR, f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    import json as _json
    with open(cache_path, "w", encoding="utf-8") as fp:
        _json.dump(result, fp, ensure_ascii=False, indent=2)

    return jsonify(result)


@app.route("/api/fdd/history", methods=["GET"])
def fdd_history():
    import json as _json
    if not os.path.exists(FDD_CACHE_DIR):
        return jsonify([])
    files = sorted(
        [f for f in os.listdir(FDD_CACHE_DIR) if f.endswith(".json")],
        reverse=True
    )[:10]
    history = []
    for fname in files:
        try:
            with open(os.path.join(FDD_CACHE_DIR, fname), encoding="utf-8") as fp:
                d = _json.load(fp)
                history.append({
                    "company_name": d.get("company_name", fname),
                    "filename": d.get("filename", ""),
                    "analyzed_at": d.get("analyzed_at", ""),
                    "cache_file": fname,
                })
        except Exception:
            pass
    return jsonify(history)


@app.route("/api/fdd/cache/<cache_file>", methods=["GET"])
def fdd_get_cache(cache_file: str):
    import json as _json
    # 경로 traversal 방지
    safe = os.path.basename(cache_file)
    path = os.path.join(FDD_CACHE_DIR, safe)
    if not os.path.exists(path):
        return jsonify({"error": "캐시 없음"}), 404
    with open(path, encoding="utf-8") as fp:
        return jsonify(_json.load(fp))


# ── 비상장사 리서치 라우트 ───────────────────────────────────────────────────

@app.route("/api/research", methods=["POST"])
def research_company():
    body = request.get_json(silent=True) or {}
    company_name = body.get("company", "").strip()
    force_refresh = body.get("refresh", False)

    if not company_name:
        return jsonify({"error": "회사명을 입력해주세요."}), 400

    # 24시간 캐시 확인
    if not force_refresh:
        cached = load_research_cache(company_name)
        if cached:
            try:
                cached_at = datetime.fromisoformat(cached.get("researched_at", "2000-01-01"))
                if (datetime.now() - cached_at).total_seconds() < 86400:
                    return jsonify(cached)
            except Exception:
                pass

    from services.research_service import research_private_company
    result = research_private_company(company_name)
    if not result:
        return jsonify({"error": f"'{company_name}' 리서치에 실패했습니다."}), 500

    result["researched_at"] = datetime.now().isoformat()
    save_research_cache(company_name, result)

    # 검색 히스토리 업데이트
    history = load_research_history()
    history = [h for h in history if h.get("company") != company_name]
    history.insert(0, {"company": company_name, "researched_at": result["researched_at"]})
    save_research_history(history[:20])

    return jsonify(result)


@app.route("/api/research/history", methods=["GET"])
def get_research_history():
    return jsonify(load_research_history())


@app.route("/api/research/<path:company_name>", methods=["GET"])
def get_research_cached(company_name: str):
    cached = load_research_cache(company_name)
    if not cached:
        return jsonify({"error": "캐시된 리서치 없음"}), 404
    return jsonify(cached)


# ── 뉴스 감성 분석 라우트 ─────────────────────────────────────────────────────

@app.route("/api/news-sentiment", methods=["POST"])
def news_sentiment():
    body = request.get_json(silent=True) or {}
    query = body.get("query", "").strip()
    days  = int(body.get("days", 7))

    if not query:
        return jsonify({"error": "종목명 또는 티커를 입력해주세요."}), 400
    if days not in (7, 30):
        days = 7

    from services.news_sentiment_service import run_news_sentiment
    result = run_news_sentiment(query, days)

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


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
