COMMON_QUERIES = [
    "{region} 맛집",
    "{region} 식당",
    "{region} 현지인 맛집",
    "{region} 로컬 맛집",
    "{region} 한식 맛집",
    "{region} 카페",
    "{region} 감성 카페",
    "{region} 디저트 카페",
    "{region} 조용한 카페",
    "{region} 관광지",
    "{region} 여행지",
    "{region} 가볼만한 곳",
    "{region} 명소",
    "{region} 체험",
    "{region} 문화시설",
    "{region} 전통시장",
    "{region} 특산물",
    "{region} 숙소",
    "{region} 호텔",
    "{region} 펜션",
    "{region} 게스트하우스",
    "{region} 한옥 숙소",
    "{region} 1박2일 여행",
    "{region} 2박3일 여행",
    "{region} 당일치기 여행",
    "{region} 주말 여행",
    "{region} 가족 여행",
    "{region} 아이와 가볼만한 곳",
    "{region} 부모님과 가볼만한 곳",
    "{region} 커플 여행",
    "{region} 데이트 코스",
    "{region} 친구 여행",
    "{region} 혼자 여행",
    "{region} 뚜벅이 여행",
    "{region} 드라이브 코스",
    "{region} 산책 명소",
    "{region} 야경 명소",
    "{region} 실내 가볼만한 곳",
    "{region} 비오는날 가볼만한 곳",
    "{region} 역사 여행",
    "{region} 힐링 여행",
    "{region} 자연 여행",
    "{region} 로컬 여행",
    "{region} 먹거리 여행",
    "{region} 시장 투어",
    "{region} 문화 여행",
    "{region} 사진 명소",
]

FIRST_PHASE_REGIONS = [
    "공주",
    "부여",
    "천안",
    "아산",
    "청주",
    "제천",
    "단양",
    "대전",
    "세종",
]

REGION_SPECIFIC_QUERIES = {
    "공주": [
        "공주 역사 여행",
        "공주 문화유산",
        "공주 한옥 숙소",
        "공주 전통 체험",
        "공주 공방 체험",
        "공주 백제 여행",
        "공주 문화재 코스",
        "공주 시장 투어",
    ],
    "부여": [
        "부여 역사 여행",
        "부여 문화유산",
        "부여 한옥 숙소",
        "부여 전통 체험",
        "부여 공방 체험",
        "부여 백제 여행",
        "부여 문화재 코스",
        "부여 시장 투어",
    ],
    "천안": [
        "천안 빵집",
        "천안 베이커리 카페",
        "천안 데이트 코스",
        "천안 실내 데이트",
        "천안 야경 명소",
        "천안 드라이브 코스",
    ],
    "아산": [
        "아산 온천 여행",
        "아산 온천 숙소",
        "아산 힐링 여행",
        "아산 가족 여행 코스",
        "아산 드라이브 코스",
        "아산 로컬 맛집",
    ],
    "청주": [
        "청주 전시",
        "청주 박물관",
        "청주 미술관",
        "청주 실내 데이트",
        "청주 문화 여행",
        "청주 야경 명소",
        "청주 성안길 맛집",
    ],
    "제천": [
        "제천 자연 여행",
        "제천 힐링 여행",
        "제천 드라이브 코스",
        "제천 호수 여행",
        "제천 사진 명소",
        "제천 온천 여행",
        "제천 가족 여행 코스",
    ],
    "단양": [
        "단양 자연 여행",
        "단양 드라이브 코스",
        "단양 사진 명소",
        "단양 커플 여행",
        "단양 액티비티",
        "단양 산책 명소",
        "단양 전망 명소",
    ],
    "대전": [
        "대전 전시",
        "대전 박물관",
        "대전 미술관",
        "대전 실내 데이트",
        "대전 야경 명소",
        "대전 빵집",
        "대전 베이커리 카페",
        "대전 성심당 근처 맛집",
    ],
    "세종": [
        "세종 호수공원 근처 카페",
        "세종 실내 가볼만한 곳",
        "세종 가족 나들이",
        "세종 산책 명소",
        "세종 로컬 맛집",
        "세종 데이트 코스",
    ],
}


def build_queries(region_name: str) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()

    for template in COMMON_QUERIES:
        query = template.format(region=region_name)
        if query not in seen:
            queries.append(query)
            seen.add(query)

    for query in REGION_SPECIFIC_QUERIES.get(region_name, []):
        if query not in seen:
            queries.append(query)
            seen.add(query)

    return queries
