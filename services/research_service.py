import os
import requests
from anthropic import Anthropic

_client = None
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def research_private_company(company_name: str) -> dict | None:
    """비상장사 웹 리서치 + Claude AI 분석 리포트 생성"""
    try:
        search_data = _multi_search(company_name)
        report = _generate_report(company_name, search_data["content"])
        return {
            "company_name": company_name,
            "report": report,
            "sources": search_data["sources"],
        }
    except Exception as e:
        print(f"[research_service] {company_name} 리서치 실패: {e}")
        return None


def _multi_search(company_name: str) -> dict:
    """Tavily API로 핵심 쿼리 3개 검색 (속도 최적화)"""
    queries = [
        f"{company_name} company overview funding valuation investors",
        f"{company_name} revenue financials business model 2024 2025",
        f"{company_name} news latest announcement competitors",
    ]

    all_content = []
    sources = []
    seen_urls = set()

    for query in queries:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 5,
                    "include_raw_content": False,
                    "include_answer": True,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("answer"):
                    all_content.append(f"[AI 요약] {data['answer']}")
                for r in data.get("results", []):
                    url = r.get("url", "")
                    if url not in seen_urls:
                        seen_urls.add(url)
                        all_content.append(
                            f"[{r.get('title', '')}]\n{r.get('content', '')}\nURL: {url}"
                        )
                        sources.append({"title": r.get("title", ""), "url": url})
            else:
                print(f"[research_service] Tavily 오류 {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            print(f"[research_service] 검색 오류 ({query[:40]}...): {e}")

    return {
        "content": "\n\n---\n\n".join(all_content[:20]),
        "sources": sources[:12],
    }


def _generate_report(company_name: str, search_content: str) -> str:
    """Claude로 구조화된 분석 리포트 생성"""

    prompt = f"""당신은 신한투자증권 리서치센터의 시니어 투자 애널리스트입니다.
아래의 웹 검색 결과를 바탕으로 **{company_name}** 에 대한 비상장사 투자 리서치 리포트를 작성해주세요.

### 수집된 원자료
{search_content}

---

아래 **6개 섹션**으로 구성된 한국어 리포트를 작성하세요.
- 각 섹션은 반드시 `## N. 섹션명` 형식의 헤더로 시작하세요.
- 각 항목은 bullet point(-)로 작성하세요.
- 확인되지 않은 수치는 "(추정)" 또는 "(미확인)"으로 명시하세요.
- 확인 불가한 항목은 "공개 정보 없음"으로 표기하세요.
- 숫자/금액은 구체적으로 기재하세요 ($1.8B, 약 2조원 등).

## 1. 회사 개요
- 설립연도 / 본사 위치 / 설립자
- 핵심 미션 및 비전
- 직원 수
- 주요 고객 / 파트너사

## 2. 주요 사업
- 핵심 제품 및 서비스 상세 설명
- 기술적 차별점 및 핵심 경쟁력(moat)
- 비즈니스 모델 (수익 구조)
- 주요 경쟁사 및 포지셔닝

## 3. 주요 재무정보
- 매출 / ARR (연도별, 공개된 수치)
- 매출 성장률
- 수익성 현황 (흑자/적자 여부)
- 기타 공개된 KPI 지표

## 4. 최근 밸류에이션
- 최근 라운드 기준 기업가치 (Pre/Post-money)
- 과거 라운드 대비 밸류에이션 변화 추이
- 주요 멀티플 (Revenue Multiple, ARR Multiple 등)
- 유사 상장사 대비 비교 (가능한 경우)

## 5. 투자 펀딩 이력
- 각 라운드: 시리즈 | 날짜 | 금액 | 주요 투자자
- 누적 총 투자유치액
- 주목할 만한 전략적 투자자

## 6. 관련 업계 뉴스 및 동향
- 최근 6개월 주요 뉴스 및 마일스톤
- 업계 트렌드 및 TAM(시장 규모)
- 주요 리스크 요인
- 투자 관점 종합 의견 (1~2줄)"""

    with _get_client().messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        final_msg = stream.get_final_message()
        for block in final_msg.content:
            if block.type == "text":
                return block.text

    return "리포트 생성 실패"
