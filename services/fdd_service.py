"""
Financial Due Diligence (FDD) Multi-Agent Service
===================================================
Agent 1 — Document Parser    : PDF/Excel → 구조화된 재무 텍스트 추출
Agent 2 — Financial Analyst  : 비율 계산, 트렌드 분석, 이상값 탐지
Agent 3 — FDD Report Writer  : 전문 실사 리포트 생성 (한국어)
"""

import io
import os

import pandas as pd
from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

MAX_CONTEXT_CHARS = 80_000   # Claude 컨텍스트 안전 한도


# ═══════════════════════════════════════════════════════════════
#  공개 진입점
# ═══════════════════════════════════════════════════════════════

def run_fdd(file_bytes: bytes, filename: str, company_name: str = "") -> dict:
    """3-Agent FDD 파이프라인 실행 후 결과 반환"""

    # ── Step 1: 문서 파싱 ──
    raw_text = _parse_document(file_bytes, filename)
    if not raw_text.strip():
        return {"error": "문서에서 텍스트를 추출할 수 없습니다. 스캔 PDF는 지원하지 않습니다."}

    # ── Agent 1: Document Intelligence ──
    structured_data = _agent1_extract(raw_text, company_name, filename)

    # ── Agent 2: Financial Analysis ──
    analysis = _agent2_analyze(structured_data, company_name)

    # ── Agent 3: FDD Report ──
    report = _agent3_report(structured_data, analysis, company_name)

    return {
        "company_name": company_name or _infer_company_name(structured_data),
        "filename": filename,
        "structured_data": structured_data,
        "analysis": analysis,
        "report": report,
    }


# ═══════════════════════════════════════════════════════════════
#  문서 파싱 유틸
# ═══════════════════════════════════════════════════════════════

def _parse_document(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        return _parse_pdf(file_bytes)
    elif ext in ("xlsx", "xls", "xlsm"):
        return _parse_excel(file_bytes, ext)
    else:
        return file_bytes.decode("utf-8", errors="ignore")


def _parse_pdf(file_bytes: bytes) -> str:
    import pdfplumber
    texts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # 표 먼저 추출 (숫자 구조 보존)
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        cleaned = [str(c).strip() if c else "" for c in row]
                        texts.append("\t".join(cleaned))
            # 나머지 텍스트
            text = page.extract_text()
            if text:
                texts.append(text)
    return "\n".join(texts)[:MAX_CONTEXT_CHARS]


def _parse_excel(file_bytes: bytes, ext: str) -> str:
    engine = "openpyxl" if ext in ("xlsx", "xlsm") else "xlrd"
    xl = pd.ExcelFile(io.BytesIO(file_bytes), engine=engine)
    parts = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, header=None)
        parts.append(f"\n=== 시트: {sheet} ===\n")
        parts.append(df.to_string(index=False, na_rep=""))
    return "\n".join(parts)[:MAX_CONTEXT_CHARS]


def _infer_company_name(structured_data: str) -> str:
    lines = structured_data.split("\n")[:5]
    return lines[0].strip() if lines else "Unknown"


# ═══════════════════════════════════════════════════════════════
#  Agent 1: Document Intelligence — 재무제표 구조화
# ═══════════════════════════════════════════════════════════════

def _agent1_extract(raw_text: str, company_name: str, filename: str) -> str:
    system = """당신은 재무제표 전문 파서입니다.
업로드된 문서(재무제표, 감사보고서, 사업보고서 등)에서 핵심 재무 데이터를 추출하고 구조화하는 것이 역할입니다.
가능한 모든 숫자와 항목을 보존하면서 명확하게 정리하세요."""

    prompt = f"""아래는 '{filename}' 에서 추출한 원시 텍스트입니다.
회사명: {company_name or '미입력'}

### 원시 텍스트
{raw_text}

---
위 문서에서 아래 항목들을 추출하여 **구조화된 텍스트**로 정리해주세요:

1. **손익계산서 (P&L)**: 연도별 매출, 매출원가, 매출총이익, 판관비, 영업이익, EBITDA(추정), 당기순이익
2. **재무상태표 (B/S)**: 총자산, 유동자산, 비유동자산, 총부채, 유동부채, 비유동부채, 자본총계
3. **현금흐름표 (C/F)**: 영업활동CF, 투자활동CF, 재무활동CF, 기말현금
4. **주요 주석**: 감사의견, 우발채무, 관계사 거래, 특이사항

숫자는 단위와 함께 정확히 기재하고, 연도를 명시하세요.
항목이 없는 경우 "미확인"으로 표기하세요."""

    return _call_claude(system, prompt, max_tokens=3000, use_thinking=False)


# ═══════════════════════════════════════════════════════════════
#  Agent 2: Financial Analyst — 비율 계산 및 트렌드 분석
# ═══════════════════════════════════════════════════════════════

def _agent2_analyze(structured_data: str, company_name: str) -> str:
    system = """당신은 신한투자증권 IB본부의 시니어 재무 애널리스트입니다.
구조화된 재무 데이터를 받아 심층 재무 분석을 수행합니다.
비율 계산, 트렌드 분석, 이상값 탐지, Quality of Earnings 분석이 전문입니다."""

    prompt = f"""아래는 '{company_name}' 의 구조화된 재무 데이터입니다.

### 재무 데이터
{structured_data}

---
아래 항목들을 **정량적으로** 분석해주세요:

### A. 수익성 지표
- 매출총이익률 (Gross Margin %)
- 영업이익률 (Operating Margin %)
- EBITDA Margin %
- 순이익률 (Net Margin %)
- ROE, ROA (계산 가능한 경우)
- 연도별 추이 및 개선/악화 여부

### B. 유동성 및 안전성
- 유동비율 (Current Ratio)
- 당좌비율 (Quick Ratio)
- 부채비율 (D/E Ratio)
- 이자보상배율 (Interest Coverage)
- 순차입금/EBITDA

### C. 성장성
- 매출 CAGR (연평균성장률)
- 영업이익 성장률
- 자산 성장률

### D. 현금흐름 품질
- 영업CF vs 순이익 비교 (이익의 질)
- FCF (잉여현금흐름) 수준
- Cash Conversion 분석

### E. 이상 징후 탐지 🚨
- 매출 대비 매출채권 급증 여부
- 재고자산 이상 증가 여부
- 영업이익 흑자인데 영업CF 마이너스 여부
- 비경상 항목 규모
- 감사의견 이슈

각 항목마다 수치와 함께 **긍정(✅)/중립(⚠️)/부정(🚨)** 신호를 표시하세요."""

    return _call_claude(system, prompt, max_tokens=3000, use_thinking=True)


# ═══════════════════════════════════════════════════════════════
#  Agent 3: FDD Report Writer — 전문 실사 리포트
# ═══════════════════════════════════════════════════════════════

def _agent3_report(structured_data: str, analysis: str, company_name: str) -> str:
    system = """당신은 신한투자증권 리서치센터의 재무실사(FDD) 전문가입니다.
M&A, 투자 검토 시 사용되는 전문적인 재무실사 리포트를 작성합니다.
리포트는 투자 의사결정에 직접 활용될 수 있는 수준이어야 합니다."""

    prompt = f"""아래 재무 데이터와 분석 결과를 바탕으로 '{company_name}' 에 대한
전문적인 **재무실사(Financial Due Diligence) 리포트**를 작성해주세요.

### 구조화된 재무 데이터
{structured_data}

### 재무 분석 결과
{analysis}

---
아래 **8개 섹션** 형식으로 작성하세요. 각 섹션은 `## N. 섹션명` 헤더로 시작:

## 1. 핵심 요약 (Executive Summary)
- FDD 전체 결과 3~5줄 요약
- 주요 긍정 요인 (Green Flags)
- 주요 우려 요인 (Red Flags)
- 종합 재무 건전성 등급: S(우수) / A(양호) / B(보통) / C(주의) / D(위험)

## 2. 수익성 분석
- 매출 및 이익 추이 (연도별 수치 포함)
- 마진 구조 분석
- 핵심 드라이버 및 리스크

## 3. 재무상태 분석
- 자산 구조 및 품질
- 부채 구조 및 만기 프로파일
- 자본 적정성

## 4. 현금흐름 분석
- 영업CF 창출 능력
- FCF 수준 및 추이
- 이익의 질 (Quality of Earnings)

## 5. 유동성 및 레버리지
- 단기 유동성 평가
- 레버리지 수준 및 적정성
- 이자보상능력

## 6. 이상 징후 및 리스크 요인
- 회계 처리 이슈
- 우발채무 및 잠재 부채
- 비경상 항목 분석
- 감사의견 이슈

## 7. 투자/인수 시 주요 고려사항
- 가치평가 관련 조정사항
- Price Adjustment 가능 항목
- 확인이 필요한 추가 실사 항목 (Checklist)

## 8. 종합 의견 및 권고사항
- 재무실사 종합 결론
- 투자/인수 진행 시 주요 조건
- 권고사항

숫자와 근거를 반드시 포함하고, 전문적이고 객관적인 어조로 작성하세요."""

    return _call_claude(system, prompt, max_tokens=5000, use_thinking=True)


# ═══════════════════════════════════════════════════════════════
#  공통 Claude 호출
# ═══════════════════════════════════════════════════════════════

def _call_claude(system: str, prompt: str, max_tokens: int = 3000, use_thinking: bool = False) -> str:
    kwargs = dict(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    # thinking 파라미터 제거 (adaptive는 유효하지 않은 값)

    with client.messages.stream(**kwargs) as stream:
        final_msg = stream.get_final_message()
        for block in final_msg.content:
            if block.type == "text":
                return block.text
    return ""
