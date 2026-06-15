# Tripio AI

TRIPIO의 AI 여행 설계 서버입니다.

이 서버는 사용자의 여행 조건과 충청도 지역/장소 데이터를 바탕으로 **Travel ETF 초안 리포트**를 생성합니다.

## 역할

- 충청도 지역/장소/축제/트렌드 데이터를 RAG로 검색합니다.
- LangGraph 기반 workflow로 생성, 검증, repair 단계를 관리합니다.
- `TravelDesignAgent`는 Travel ETF 초안 리포트만 생성합니다.
- 최종 검증과 `DesignSession` 저장은 Spring Boot 백엔드가 담당합니다.

현재 1차 구조에서는 실제 LLM 호출 없이 deterministic generator로 응답을 생성합니다. 이후 OpenAI Structured Outputs, pgvector 기반 RAG, 실제 LangGraph workflow를 단계적으로 붙일 예정입니다.

## 호출 흐름

```text
Frontend
-> Spring Boot Backend
-> Tripio AI Server
-> TravelDesignAgent
-> RAG / LLM / Validator
-> Spring Boot Backend
-> DesignSession 저장
```

## 주요 API

```text
GET /health
POST /ai/travel-design/draft
```

`POST /ai/travel-design/draft`는 Travel ETF 초안 리포트를 생성합니다.

## 로컬 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

또는 `Makefile`을 사용할 수 있습니다.

```bash
make install
make dev
```

## 테스트

```bash
pytest
```

또는:

```bash
make test
```

## 린트

```bash
ruff check .
```

또는:

```bash
make lint
```

## 샘플 요청

```bash
curl -X POST http://127.0.0.1:8000/ai/travel-design/draft \
  -H "Content-Type: application/json" \
  -d @examples/travel_design_request.json
```

## 스키마 확인

개발 중에는 FastAPI endpoint로 요청/응답 JSON Schema를 확인할 수 있습니다.

```text
GET /schemas/travel-design/request
GET /schemas/travel-design/response
```

정적 schema 파일은 아래 명령으로 생성합니다.

```bash
make schemas
```

생성 위치:

```text
schemas/travel_design_request.schema.json
schemas/travel_design_response.schema.json
```

## 현재 구현 범위

- FastAPI 서버 구조
- Pydantic 요청/응답 스키마
- 요청/응답 JSON Schema export
- 충청도 seed 장소 데이터
- RAG 검색 경계
- LangGraph workflow 골격
- TravelDesignAgent 경계
- 예산 재계산 로직
- 일정 검증 로직
- API 테스트

## 다음 구현 후보

- 실제 LangGraph state graph 적용
- pgvector 또는 Chroma 기반 RAG 구현
- OpenAI Structured Outputs 기반 LLM 생성
- 검증 실패 시 repair loop 구현
- Spring Boot 백엔드 연동
- 부분 설계 모드 구현
