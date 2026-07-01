from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class KakaoCollectionConfig:
    enabled: bool = True
    pages: int = 1
    size: int = 15
    concurrency: int = 1


@dataclass(frozen=True)
class NaverCollectionConfig:
    enabled: bool = True
    pages: int = 1
    display: int = 5
    concurrency: int = 1
    min_interval_seconds: float = 0.7
    retry_attempts: int = 2


@dataclass(frozen=True)
class TourApiCollectionConfig:
    enabled: bool = True
    pages: int = 1
    rows: int = 20
    concurrency: int = 1
    festivals: bool = False
    stays: bool = False


@dataclass(frozen=True)
class CollectionSourcesConfig:
    kakao: KakaoCollectionConfig = field(default_factory=KakaoCollectionConfig)
    naver: NaverCollectionConfig = field(default_factory=NaverCollectionConfig)
    tour_api: TourApiCollectionConfig = field(default_factory=TourApiCollectionConfig)


@dataclass(frozen=True)
class CollectionRunConfig:
    region: str | None = None
    province: str = "충청남도"
    output_root: str = "data"
    save_db: bool = False
    queries: list[str] | None = None
    tour_keywords: list[str] | None = None
    festival_start_date: str | None = None
    festival_end_date: str | None = None
    sources: CollectionSourcesConfig = field(default_factory=CollectionSourcesConfig)


def load_collection_run_config(path: str | Path) -> CollectionRunConfig:
    config_path = Path(path)
    merged_raw: dict[str, Any] = {}

    base_path = _default_base_config_path(config_path)
    if base_path and base_path.exists():
        merged_raw = _deep_merge_dicts(merged_raw, _parse_simple_yaml(base_path.read_text(encoding="utf-8")))

    merged_raw = _deep_merge_dicts(
        merged_raw,
        _parse_simple_yaml(config_path.read_text(encoding="utf-8")),
    )
    return _build_run_config(merged_raw)


def replace_run_config(config: CollectionRunConfig, **changes: Any) -> CollectionRunConfig:
    return replace(config, **changes)


def _default_base_config_path(config_path: Path) -> Path | None:
    if config_path.parent.name != "regions":
        return None
    return config_path.parent.parent / "base.yaml"


def _build_run_config(raw: dict[str, Any]) -> CollectionRunConfig:
    sources_raw = raw.get("sources", {})
    festival_raw = raw.get("festival", {})

    return CollectionRunConfig(
        region=raw.get("region"),
        province=str(raw.get("province", "충청남도")),
        output_root=str(raw.get("output_root", "data")),
        save_db=bool(raw.get("save_db", False)),
        queries=_as_string_list(raw.get("queries")),
        tour_keywords=_as_string_list(raw.get("tour_keywords")),
        festival_start_date=_as_optional_string(
            raw.get("festival_start_date", festival_raw.get("start_date"))
        ),
        festival_end_date=_as_optional_string(raw.get("festival_end_date", festival_raw.get("end_date"))),
        sources=CollectionSourcesConfig(
            kakao=KakaoCollectionConfig(
                enabled=bool(sources_raw.get("kakao", {}).get("enabled", True)),
                pages=int(sources_raw.get("kakao", {}).get("pages", 1)),
                size=int(sources_raw.get("kakao", {}).get("size", 15)),
                concurrency=max(1, int(sources_raw.get("kakao", {}).get("concurrency", 1))),
            ),
            naver=NaverCollectionConfig(
                enabled=bool(sources_raw.get("naver", {}).get("enabled", True)),
                pages=int(sources_raw.get("naver", {}).get("pages", 1)),
                display=int(sources_raw.get("naver", {}).get("display", 5)),
                concurrency=max(1, int(sources_raw.get("naver", {}).get("concurrency", 1))),
                min_interval_seconds=float(
                    sources_raw.get("naver", {}).get("min_interval_seconds", 0.7)
                ),
                retry_attempts=max(0, int(sources_raw.get("naver", {}).get("retry_attempts", 2))),
            ),
            tour_api=TourApiCollectionConfig(
                enabled=bool(sources_raw.get("tour_api", {}).get("enabled", True)),
                pages=int(sources_raw.get("tour_api", {}).get("pages", 1)),
                rows=int(sources_raw.get("tour_api", {}).get("rows", 20)),
                concurrency=max(1, int(sources_raw.get("tour_api", {}).get("concurrency", 1))),
                festivals=bool(sources_raw.get("tour_api", {}).get("festivals", False)),
                stays=bool(sources_raw.get("tour_api", {}).get("stays", False)),
            ),
        ),
    )


def _as_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"Expected list value, got {type(value).__name__}")
    return [str(item) for item in value]


def _as_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        stripped = _strip_comment(raw_line.rstrip())
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append((indent, stripped.strip()))

    if not lines:
        return {}

    parsed, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError("Unable to parse full YAML document")
    if not isinstance(parsed, dict):
        raise ValueError("Top-level YAML document must be a mapping")
    return parsed


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or line[index - 1].isspace():
                return line[:index].rstrip()
    return line


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    _, first_content = lines[index]
    if first_content.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent or not content.startswith("- "):
            break
        item_content = content[2:].strip()
        index += 1
        if item_content:
            items.append(_parse_scalar(item_content))
            continue
        if index >= len(lines) or lines[index][0] <= indent:
            items.append(None)
            continue
        child, index = _parse_block(lines, index, lines[index][0])
        items.append(child)
    return items, index


def _parse_mapping(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    mapping: dict[str, Any] = {}
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent or content.startswith("- "):
            break
        if ":" not in content:
            raise ValueError(f"Expected key/value mapping line, got: {content}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        value_text = raw_value.strip()
        index += 1
        if value_text:
            mapping[key] = _parse_scalar(value_text)
            continue
        if index < len(lines) and lines[index][0] > indent:
            child, index = _parse_block(lines, index, lines[index][0])
            mapping[key] = child
            continue
        mapping[key] = {}
    return mapping, index


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
