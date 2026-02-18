from __future__ import annotations

from typing import List

POLLSTERS: List[str] = [
    "리서치앤리서치",
    "엠브레인퍼블릭",
    "리서치뷰",
    "에이스리서치",
    "한국리서치",
    "조원씨앤아이",
    "알앤써치",
    "리얼미터",
    "코리아리서치인터내셔널",
]

SHEETS: List[str] = [
    "정당지지도 (25.1.1~12.31.)",
    "정당지지도 (26.1.1~)",
]

BASE_COLS = {
    "등록번호",
    "조사기관",
    "의뢰자",
    "조사일자",
    "조사방법",
    "표본추출틀",
    "표본수(명)",
    "접촉률(%)",
    "응답률(%)",
    "95%신뢰수준\n표본오차(%p)",
    "date_start",
    "date_end",
    "date_mid",
}
