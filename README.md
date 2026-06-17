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

## 외부 장소 데이터 수집

TourAPI, 카카오 Local API, 네이버 지역 검색 API를 사용해 충청도 지역 장소 후보를 수집합니다.

먼저 `.env` 파일에 실제 키를 설정합니다. 키는 GitHub에 올리지 않습니다.

```env
DATABASE_URL=postgresql+psycopg://tripio:tripio@localhost:5432/tripio_ai
KAKAO_REST_API_KEY=
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
TOUR_API_SERVICE_KEY=
```

공주 기본 검색어 묶음으로 수집하려면:

```bash
.venv/bin/python scripts/collect_places.py --region 공주
```

검색어를 직접 지정할 수도 있습니다.

```bash
.venv/bin/python scripts/collect_places.py \
  --region 공주 \
  --query "공주 관광지" \
  --query "공주 카페"
```

수집 결과는 로컬 개발용 JSON 파일로 저장됩니다.

```text
data/raw/kakao
data/raw/naver
data/raw/tour_api
data/processed
```

`data/raw`는 외부 API 원본 응답이고, `data/processed`는 Tripio 표준 장소 스키마로 정규화하고 중복 제거한 결과입니다. 이 파일들은 수집 파이프라인 검증용 산출물이므로 기본적으로 Git에 커밋하지 않습니다.

DB 마이그레이션을 적용한 뒤 수집 결과를 PostgreSQL에도 저장하려면:

```bash
.venv/bin/python scripts/collect_places.py --region 공주 --save-db
```

## DB 마이그레이션

AI 서버는 수집/정제한 장소, 축제, 지역 지표, RAG 문서를 PostgreSQL에 저장합니다.
RAG 확장을 위해 초기 스키마에서 `pgvector` 확장과 `rag_documents.embedding` 컬럼을 준비합니다.

```bash
alembic upgrade head
```

AI DB는 벡터 검색을 위해 `pgvector` 확장이 필요합니다. 로컬 PostgreSQL을 Docker로 실행한다면
`pgvector/pgvector:pg16` 이미지를 사용해야 합니다.

로컬 개발에서는 백엔드와 같은 PostgreSQL 컨테이너를 사용하되 database를 분리합니다.

```text
tripio_backend: Spring Boot/Flyway 서비스 운영 데이터
tripio_ai: FastAPI/Alembic 추천/분석 데이터
```

이미 기존 PostgreSQL 볼륨이 다른 계정이나 일반 PostgreSQL 이미지로 초기화되어 있다면
`DATABASE_URL`의 계정이 존재하지 않거나 `CREATE EXTENSION vector` 단계에서 실패할 수 있습니다.
초기 개발 DB를 다시 만들어도 되는 상황에서만 기존 볼륨을 삭제하고 재생성하세요.

초기 주요 테이블:

```text
regions
places
place_sources
events
region_metrics
rag_documents
ingestion_runs
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
