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
.venv/bin/python scripts/collect_places.py --config configs/collection/regions/gongju.yaml
```

검색어를 직접 지정할 수도 있습니다.

```bash
.venv/bin/python scripts/collect_places.py \
  --config configs/collection/regions/gongju.yaml \
  --query "공주 관광지" \
  --query "공주 카페"
```

페이지 수나 동시성 같은 일부 값은 CLI로 덮어쓸 수 있습니다.

```bash
.venv/bin/python scripts/collect_places.py \
  --config configs/collection/regions/gongju.yaml \
  --kakao-pages 9 \
  --kakao-concurrency 4
```

### 수집 설정 구조

수집 설정은 공통 + 지역별 override 방식으로 관리합니다.

```text
configs/collection/base.yaml
configs/collection/regions/gongju.yaml
configs/collection/regions/buyeo.yaml
configs/collection/regions/cheonan.yaml
configs/collection/regions/asan.yaml
configs/collection/regions/cheongju.yaml
configs/collection/regions/jecheon.yaml
configs/collection/regions/danyang.yaml
configs/collection/regions/daejeon.yaml
configs/collection/regions/sejong.yaml
configs/collection/regions/boryeong.yaml
configs/collection/regions/seosan.yaml
configs/collection/regions/chungju.yaml
configs/collection/regions/goesan.yaml
configs/collection/regions/yesan.yaml
configs/collection/regions/nonsan.yaml
configs/collection/regions/seocheon.yaml
configs/collection/regions/taean.yaml
configs/collection/regions/dangjin.yaml
configs/collection/regions/hongseong.yaml
configs/collection/regions/cheongyang.yaml
configs/collection/regions/geumsan.yaml
configs/collection/regions/gyeryong.yaml
configs/collection/regions/boeun.yaml
configs/collection/regions/okcheon.yaml
configs/collection/regions/yeongdong.yaml
configs/collection/regions/eumseong.yaml
configs/collection/regions/jincheon.yaml
configs/collection/regions/jeungpyeong.yaml
```

- `base.yaml`
  - 전체 지역 공통 기본값
  - 소스별 활성화 여부
  - 페이지 수, 행 수, 동시성, retry/rate-limit 기본값
- `regions/*.yaml`
  - 지역명, 시도명
  - DB 저장 여부
  - 지역별 페이지 수 override
  - 축제/숙소 수집 여부
  - 축제 날짜 범위

### 현재 수집 실행 방식

현재 수집기는 다음 원칙으로 동작합니다.

```text
지역 단위 실행: 순차
소스 단위 실행: 제한 병렬
```

예를 들어 `공주 -> 부여 -> 대전`은 순차로 돌리고, 각 지역 내부에서는 아래 세 소스를 동시에 실행합니다.

- Kakao Local API
- Naver Local Search API
- TourAPI

단, 소스별 제한은 다르게 둡니다.

- 카카오: 제한 병렬
- 네이버: 보수적 병렬 + retry/backoff + 최소 간격
- TourAPI: 제한 병렬

수집 결과는 로컬 개발용 JSON 파일로 저장됩니다.

```text
data/raw/kakao
data/raw/naver
data/raw/tour_api
data/processed
data/processed/reports
```

현재 장소 수집 파이프라인은 아래 순서로 동작합니다.

```text
API collection
-> normalization
-> dedupe
-> quality refinement
-> JSON/DB save
```

`data/raw`는 외부 API 원본 응답입니다. `data/processed` 아래에는 정규화, 중복 제거, 품질 정제를 통과한 최종 장소 JSON과 품질 리포트가 저장됩니다. 이 파일들은 수집 파이프라인 검증용 산출물이므로 기본적으로 Git에 커밋하지 않습니다.

주요 산출물은 다음과 같습니다.

- `data/processed/<region>_places.json`
  - 지역 필터, 정규화, 중복 제거, 품질 정제를 거친 최종 장소 목록
- `data/processed/reports/<region>_quality_report.json`
  - 품질 정제 단계에서 생성한 상세 리포트

품질 리포트에는 아래 정보가 포함됩니다.

- `summary`
  - `input_count`, `kept_count`, `filtered_count`, `reclassified_count`
- `filtered_samples`
  - 품질 정제에서 제외된 장소 샘플
- `reclassified_samples`
  - `ETC`에서 다른 카테고리로 재분류된 장소 샘플

CLI 실행 출력에도 같은 품질 요약이 함께 표시됩니다.

```text
quality_input=<count>
quality_kept=<count>
quality_filtered=<count>
quality_reclassified=<count>
```

DB 마이그레이션을 적용한 뒤 수집 결과를 PostgreSQL에도 저장하려면:

```bash
.venv/bin/python scripts/collect_places.py --config configs/collection/regions/gongju.yaml
```

참고로 현재 수집 파이프라인에 직접 연결된 것은 API 원본 응답(`data/raw`)이며, `data/external` 아래 공공데이터 CSV/XLSX는 아직 자동 병합 대상이 아닙니다. 공공데이터 파일은 후속 보강, 검증, 메타데이터 확장용 자산으로 관리합니다.

### 1차 지역 실행 순서표

처음 수집 배치는 아래 순서로 진행하는 것을 권장합니다.

| 순서 | 지역 | 설정 파일 | 목적 |
|---|---|---|---|
| 1 | 공주 | `configs/collection/regions/gongju.yaml` | 기준선 검증 완료 지역, 수집 구조 재확인 |
| 2 | 부여 | `configs/collection/regions/buyeo.yaml` | 역사/문화유산 지역 확장 |
| 3 | 천안 | `configs/collection/regions/cheonan.yaml` | 도시형 맛집/카페/데이트 데이터 확장 |
| 4 | 아산 | `configs/collection/regions/asan.yaml` | 온천/힐링/가족 여행 데이터 확장 |
| 5 | 세종 | `configs/collection/regions/sejong.yaml` | 행정도시형 실내/산책/가족 나들이 데이터 확장 |
| 6 | 대전 | `configs/collection/regions/daejeon.yaml` | 광역시형 문화/전시/베이커리 데이터 확장 |
| 7 | 청주 | `configs/collection/regions/cheongju.yaml` | 충북 중심 도시형 데이터 확장 |
| 8 | 제천 | `configs/collection/regions/jecheon.yaml` | 자연/호수/힐링 여행 데이터 확장 |
| 9 | 단양 | `configs/collection/regions/danyang.yaml` | 자연/전망/액티비티 데이터 확장 |

권장 이유는 다음과 같습니다.

- 먼저 `공주/부여`로 역사 관광형 지역을 확보
- `천안/아산/세종/대전`으로 도시형/생활형 여행 데이터를 확보
- `청주/제천/단양`으로 충북권 자연/문화/액티비티 축을 보강

### 2차 지역 후보 목록

2차 확장 지역은 아래 순서로 수집하는 것을 권장합니다.

| 순서 | 지역 | 설정 파일 | 목적 |
|---|---|---|---|
| 1 | 보령 | `configs/collection/regions/boryeong.yaml` | 해변/오션뷰/축제형 여행 데이터 확장 |
| 2 | 서산 | `configs/collection/regions/seosan.yaml` | 읍성/사찰/서해권 드라이브 데이터 확장 |
| 3 | 충주 | `configs/collection/regions/chungju.yaml` | 호수/동굴/액티비티형 데이터 확장 |
| 4 | 괴산 | `configs/collection/regions/goesan.yaml` | 자연/계곡/산책형 힐링 데이터 확장 |
| 5 | 예산 | `configs/collection/regions/yesan.yaml` | 예당호/온천/가족 나들이 데이터 확장 |
| 6 | 논산 | `configs/collection/regions/nonsan.yaml` | 호수/딸기체험/드라이브형 데이터 확장 |

### 3차 지역 후보 목록

3차 확장 지역은 충청권 전체 시군 커버를 목표로 합니다.

| 권역 | 지역 | 설정 파일 | 목적 |
|---|---|---|---|
| 충남 | 서천 | `configs/collection/regions/seocheon.yaml` | 생태/갈대밭/해변형 여행 데이터 확장 |
| 충남 | 태안 | `configs/collection/regions/taean.yaml` | 서해 해변/오션뷰/가족 여행 데이터 확장 |
| 충남 | 당진 | `configs/collection/regions/dangjin.yaml` | 삽교호/왜목마을/드라이브형 데이터 확장 |
| 충남 | 홍성 | `configs/collection/regions/hongseong.yaml` | 남당항/시장/바다형 데이터 확장 |
| 충남 | 청양 | `configs/collection/regions/cheongyang.yaml` | 칠갑산/출렁다리/힐링형 데이터 확장 |
| 충남 | 금산 | `configs/collection/regions/geumsan.yaml` | 인삼/자연/체험형 데이터 확장 |
| 충남 | 계룡 | `configs/collection/regions/gyeryong.yaml` | 계룡산권/드라이브/근교형 데이터 확장 |
| 충북 | 보은 | `configs/collection/regions/boeun.yaml` | 속리산/법주사/산악형 데이터 확장 |
| 충북 | 옥천 | `configs/collection/regions/okcheon.yaml` | 대청호/문학/드라이브형 데이터 확장 |
| 충북 | 영동 | `configs/collection/regions/yeongdong.yaml` | 와인/포도/힐링형 데이터 확장 |
| 충북 | 음성 | `configs/collection/regions/eumseong.yaml` | 품바/자연/가족형 데이터 확장 |
| 충북 | 진천 | `configs/collection/regions/jincheon.yaml` | 농다리/호수/산책형 데이터 확장 |
| 충북 | 증평 | `configs/collection/regions/jeungpyeong.yaml` | 좌구산/벨포레/가족형 데이터 확장 |

### 데이터 수집 시작 시점

아래 조건이 모두 만족되면 실제 1차 지역 수집을 시작해도 됩니다.

```text
1. PostgreSQL 컨테이너가 정상 실행 중일 것
2. .env에 Kakao / Naver / TourAPI 키가 모두 설정되어 있을 것
3. alembic upgrade head가 완료되어 있을 것
4. YAML 설정 파일이 준비되어 있을 것
5. pytest가 통과한 상태일 것
```

현재 기준으로는 위 조건이 대부분 이미 충족되어 있고, 코드 테스트도 통과한 상태이므로 **이제 1차 지역 수집을 시작해도 되는 단계**입니다.

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
