# Place Quality Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수집된 장소 데이터를 2차 정제해서 추천/분석에 바로 쓸 수 있는 품질 기준본으로 저장하고, 필터 전후 변화와 애매한 분류를 리포트로 검증할 수 있게 만든다.

**Architecture:** 현재 `scripts/collect_places.py -> PlaceCollector -> normalize -> deduplicate -> JSON/DB 저장` 흐름 뒤에 품질 정제 레이어를 추가한다. 새 `place_quality` 서비스가 비핵심 장소 필터링, `ETC` 재분류, 요약 리포트를 담당하고, `PlaceCollector.collect()`는 정제된 결과와 품질 리포트를 함께 반환한다.

**Tech Stack:** Python 3.11, Pydantic, pytest, existing Tripio collection pipeline

---

### Task 1: 품질 정제 서비스 추가

**Files:**
- Create: `Tripio-ai/app/services/place_quality.py`
- Test: `Tripio-ai/tests/test_place_quality.py`

- [ ] **Step 1: 품질 서비스 테스트를 먼저 작성한다**

```python
from app.schemas.place_source import ExternalPlaceSource, NormalizedPlace, PlaceCategory
from app.services.place_quality import refine_places


def _place(
    *,
    name: str,
    category: PlaceCategory,
    raw_category: str,
    address: str = "충남 공주시 테스트로 1",
) -> NormalizedPlace:
    return NormalizedPlace(
        source=ExternalPlaceSource.KAKAO,
        source_place_id=name,
        name=name,
        region_name="공주",
        address=address,
        road_address=address,
        latitude=36.5,
        longitude=127.1,
        category=category,
        source_query="공주 테스트",
        raw_category=raw_category,
    )


def test_refine_places_reclassifies_etc_to_culture() -> None:
    result = refine_places(
        [
            _place(
                name="공주시민문화센터",
                category=PlaceCategory.ETC,
                raw_category="교육,학문 > 문화센터",
            )
        ]
    )

    assert len(result.kept_places) == 1
    assert result.kept_places[0].category == PlaceCategory.CULTURE
    assert result.summary.reclassified_count == 1


def test_refine_places_filters_non_trip_support_facilities() -> None:
    result = refine_places(
        [
            _place(
                name="공산성 공영주차장",
                category=PlaceCategory.ETC,
                raw_category="교통,수송 > 교통시설 > 주차장 > 공영주차장",
            )
        ]
    )

    assert result.kept_places == []
    assert len(result.filtered_places) == 1
    assert result.summary.filtered_count == 1


def test_refine_places_keeps_market_style_places() -> None:
    result = refine_places(
        [
            _place(
                name="공주고마아트",
                category=PlaceCategory.ETC,
                raw_category="쇼핑,유통>특산물,관광민예품",
            )
        ]
    )

    assert len(result.kept_places) == 1
    assert result.kept_places[0].category == PlaceCategory.MARKET
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai && .venv/bin/pytest tests/test_place_quality.py -q`

Expected: `ModuleNotFoundError` 또는 `cannot import name 'refine_places'`

- [ ] **Step 3: 최소 구현으로 품질 서비스와 리포트 모델을 만든다**

```python
from dataclasses import dataclass

from app.schemas.place_source import NormalizedPlace, PlaceCategory


@dataclass(frozen=True)
class PlaceQualitySummary:
    input_count: int
    kept_count: int
    filtered_count: int
    reclassified_count: int


@dataclass(frozen=True)
class PlaceQualityResult:
    kept_places: list[NormalizedPlace]
    filtered_places: list[NormalizedPlace]
    summary: PlaceQualitySummary


def refine_places(places: list[NormalizedPlace]) -> PlaceQualityResult:
    kept_places: list[NormalizedPlace] = []
    filtered_places: list[NormalizedPlace] = []
    reclassified_count = 0

    for place in places:
        decision = _decide_category(place)
        if decision is None:
            filtered_places.append(place)
            continue

        updated = place.model_copy(deep=True)
        if updated.category != decision:
            updated.category = decision
            updated.tags = _retag(updated.tags, decision)
            reclassified_count += 1
        kept_places.append(updated)

    return PlaceQualityResult(
        kept_places=kept_places,
        filtered_places=filtered_places,
        summary=PlaceQualitySummary(
            input_count=len(places),
            kept_count=len(kept_places),
            filtered_count=len(filtered_places),
            reclassified_count=reclassified_count,
        ),
    )
```

- [ ] **Step 4: 분류/필터 규칙을 실제로 채운다**

```python
def _decide_category(place: NormalizedPlace) -> PlaceCategory | None:
    raw = place.raw_category
    name = place.name

    if any(token in raw for token in ["주차장", "전기차 충전소", "편의점", "교차로", "입출구", "매표소"]):
        return None
    if any(token in raw for token in ["문화센터", "문화의집", "도서", "공방", "미술,공예", "박물관", "전시관"]):
        return PlaceCategory.CULTURE
    if any(token in raw for token in ["특산물", "관광민예품", "전통식품", "기념품판매"]):
        return PlaceCategory.MARKET
    if any(token in raw for token in ["체험", "오락실", "골프연습장", "캠핑", "야영장", "레저"]):
        return PlaceCategory.ACTIVITY
    if any(token in raw for token in ["절,사찰", "공원", "유적", "명소"]):
        return PlaceCategory.TOURIST_ATTRACTION
    if place.category != PlaceCategory.ETC:
        return place.category
    if "시장" in name:
        return PlaceCategory.MARKET
    return PlaceCategory.ETC
```

- [ ] **Step 5: 테스트를 다시 실행한다**

Run: `cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai && .venv/bin/pytest tests/test_place_quality.py -q`

Expected: `3 passed`

- [ ] **Step 6: 커밋한다**

```bash
cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai
git add app/services/place_quality.py tests/test_place_quality.py
git commit -m "feat: add place quality refinement service"
```

### Task 2: 수집 파이프라인에 품질 정제 단계 연결

**Files:**
- Modify: `Tripio-ai/app/schemas/place_source.py`
- Modify: `Tripio-ai/app/services/place_collector.py`
- Modify: `Tripio-ai/tests/test_place_collection.py`

- [ ] **Step 1: 수집 결과 테스트를 먼저 추가한다**

```python
def test_place_collector_applies_quality_refinement(tmp_path: Path) -> None:
    collector = PlaceCollector(
        kakao_client=FakeKakaoClient(),
        naver_client=None,
        tour_client=None,
        output_root=tmp_path,
    )

    result = collector.collect(
        region_name="공주",
        queries=["공주 테스트"],
    )

    assert all(place.category != PlaceCategory.ETC for place in result.processed_places if "문화센터" in place.raw_category)
    assert result.quality_summary is not None
    assert result.quality_summary.input_count >= result.quality_summary.kept_count
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai && .venv/bin/pytest tests/test_place_collection.py -q`

Expected: `AttributeError: 'PlaceCollectionResult' object has no attribute 'quality_summary'`

- [ ] **Step 3: 수집 결과 스키마에 품질 요약 필드를 추가한다**

```python
class PlaceQualitySummaryModel(BaseModel):
    input_count: int
    kept_count: int
    filtered_count: int
    reclassified_count: int


class PlaceCollectionResult(BaseModel):
    region_name: str
    queries: list[str]
    processed_places: list[NormalizedPlace]
    warnings: list[str] = Field(default_factory=list)
    quality_summary: PlaceQualitySummaryModel | None = None
```

- [ ] **Step 4: `PlaceCollector.collect()`에 정제 단계를 연결한다**

```python
quality_result = refine_places(processed_places)
processed_places = quality_result.kept_places

self._write_json(
    self.output_root / "processed" / f"{_slug(region_name)}_places.json",
    [place.model_dump(mode="json") for place in processed_places],
)

return PlaceCollectionResult(
    region_name=region_name,
    queries=queries,
    processed_places=processed_places,
    warnings=warnings,
    quality_summary=PlaceQualitySummaryModel(
        input_count=quality_result.summary.input_count,
        kept_count=quality_result.summary.kept_count,
        filtered_count=quality_result.summary.filtered_count,
        reclassified_count=quality_result.summary.reclassified_count,
    ),
)
```

- [ ] **Step 5: 수집 테스트를 다시 실행한다**

Run: `cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai && .venv/bin/pytest tests/test_place_collection.py -q`

Expected: `passed`

- [ ] **Step 6: 커밋한다**

```bash
cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai
git add app/schemas/place_source.py app/services/place_collector.py tests/test_place_collection.py
git commit -m "feat: apply quality refinement during place collection"
```

### Task 3: 품질 리포트 산출물 저장 및 CLI 요약 출력

**Files:**
- Modify: `Tripio-ai/app/services/place_quality.py`
- Modify: `Tripio-ai/scripts/collect_places.py`
- Test: `Tripio-ai/tests/test_collect_places_script.py`

- [ ] **Step 1: CLI 요약 출력 테스트를 추가한다**

```python
def test_collect_places_prints_quality_summary(capsys: pytest.CaptureFixture[str]) -> None:
    result = PlaceCollectionResult(
        region_name="공주",
        queries=["공주 관광지"],
        processed_places=[],
        quality_summary=PlaceQualitySummaryModel(
            input_count=10,
            kept_count=8,
            filtered_count=2,
            reclassified_count=3,
        ),
    )

    _print_collection_summary(result, "/tmp/data")
    captured = capsys.readouterr()

    assert "quality_input=10" in captured.out
    assert "quality_kept=8" in captured.out
    assert "quality_filtered=2" in captured.out
    assert "quality_reclassified=3" in captured.out
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai && .venv/bin/pytest tests/test_collect_places_script.py -q`

Expected: quality 관련 출력 assertion 실패

- [ ] **Step 3: 품질 리포트 JSON 구조를 추가한다**

```python
@dataclass(frozen=True)
class PlaceQualityReport:
    summary: PlaceQualitySummary
    filtered_samples: list[dict[str, str]]
    reclassified_samples: list[dict[str, str]]
```

```python
def build_quality_report(...) -> PlaceQualityReport:
    return PlaceQualityReport(
        summary=summary,
        filtered_samples=[
            {"name": place.name, "raw_category": place.raw_category, "address": place.address}
            for place in filtered_places[:20]
        ],
        reclassified_samples=reclassified_samples[:20],
    )
```

- [ ] **Step 4: 지역별 품질 리포트를 파일로 저장하고 CLI에도 출력한다**

```python
print(f"quality_input={result.quality_summary.input_count}")
print(f"quality_kept={result.quality_summary.kept_count}")
print(f"quality_filtered={result.quality_summary.filtered_count}")
print(f"quality_reclassified={result.quality_summary.reclassified_count}")
```

```python
self._write_json(
    self.output_root / "processed" / "reports" / f"{_slug(region_name)}_quality_report.json",
    quality_report_payload,
)
```

- [ ] **Step 5: 스크립트 테스트를 다시 실행한다**

Run: `cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai && .venv/bin/pytest tests/test_collect_places_script.py -q`

Expected: `passed`

- [ ] **Step 6: 커밋한다**

```bash
cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai
git add app/services/place_quality.py scripts/collect_places.py tests/test_collect_places_script.py
git commit -m "feat: export place quality report and summary"
```

### Task 4: 문서와 운영 명령어 정리

**Files:**
- Modify: `Tripio-ai/README.md`
- Modify: `TRIPIO-AI-DATA-COLLECTION-QUERY-SPEC.md`

- [ ] **Step 1: README에 2차 정제 단계와 결과 확인 경로를 추가한다**

```md
### 2차 정제 산출물

- `data/processed/<region>_places.json`
- `data/processed/reports/<region>_quality_report.json`

품질 리포트에는 다음이 포함됩니다.
- 필터 전/후 개수
- `ETC` 재분류 개수
- 제외된 샘플 20개
- 재분류 샘플 20개
```

- [ ] **Step 2: 쿼리 명세 문서에 “수집 후 품질 정제” 단계를 추가한다**

```md
수집 파이프라인은 다음 5단계로 동작합니다.
1. 소스별 API 수집
2. 공통 스키마 정규화
3. 중복 병합
4. 품질 정제(재분류/제외)
5. JSON/DB 저장 및 리포트 생성
```

- [ ] **Step 3: 관련 테스트 전체를 실행한다**

Run: `cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai && .venv/bin/pytest tests/test_place_quality.py tests/test_place_collection.py tests/test_collect_places_script.py -q`

Expected: all pass

- [ ] **Step 4: 마지막 커밋을 한다**

```bash
cd /Users/kmj/Desktop/Project/HanaFinalProject/Tripio-ai
git add README.md ../TRIPIO-AI-DATA-COLLECTION-QUERY-SPEC.md
git commit -m "docs: document place quality refinement flow"
```

---

## Self-Review

- Spec coverage:
  - 비핵심 장소 필터링: Task 1
  - `ETC` 재분류: Task 1
  - 수집 파이프라인 통합: Task 2
  - 리포트 저장/CLI 요약: Task 3
  - 문서 반영: Task 4
- Placeholder scan: `TBD`, `TODO`, “적절히 처리” 같은 표현 없이 구체 코드와 명령어 포함
- Type consistency:
  - 새 결과 타입은 `PlaceQualitySummaryModel`
  - 서비스 반환 타입은 `PlaceQualityResult`
  - 수집 결과는 `PlaceCollectionResult.quality_summary`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-21-place-quality-pipeline.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
