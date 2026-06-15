import json
from pathlib import Path

from app.schemas.travel_design import TravelDesignRequest, TravelDesignResponse

SCHEMA_DIR = Path("schemas")


def export_schema(name: str, schema: dict) -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    path = SCHEMA_DIR / f"{name}.schema.json"
    path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    export_schema("travel_design_request", TravelDesignRequest.model_json_schema())
    export_schema("travel_design_response", TravelDesignResponse.model_json_schema())


if __name__ == "__main__":
    main()
