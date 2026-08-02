"""
수비학(Numerology) 기반 행운수 산출 모듈
- 피타고라스 수비학 (기원전 6세기~)
- 월일 4자리 → 생명수(1~9) → 행운수 3개 (1~45 범위)
"""


def reduce_to_single(num: int) -> int:
    """숫자를 한 자릿수로 축소 (반복 합산)"""
    while num > 9:
        num = sum(int(d) for d in str(num))
    return num


def validate_mmdd(mmdd: str) -> tuple[bool, str | None]:
    """월일 4자리 유효성 (True, None) 또는 (False, 오류 메시지)."""
    if len(mmdd) != 4 or not mmdd.isdigit():
        return False, "월일은 4자리 숫자여야 합니다"

    month = int(mmdd[:2])
    day = int(mmdd[2:])

    if month < 1 or month > 12:
        return False, "월은 01~12 사이여야 합니다"
    if day < 1 or day > 31:
        return False, "일은 01~31 사이여야 합니다"

    return True, None


def get_life_path_number(mmdd: str) -> int:
    """월일 4자리 → 생명수(1~9)"""
    ok, err = validate_mmdd(mmdd)
    if not ok:
        raise ValueError(err or "월일 형식이 올바르지 않습니다")

    month = int(mmdd[:2])
    day = int(mmdd[2:])
    month_reduced = reduce_to_single(month)
    day_reduced = reduce_to_single(day)
    return reduce_to_single(month_reduced + day_reduced)


def get_lucky_numbers_from_life_path(lp: int) -> list:
    """생명수 → 행운수 3개 (1~45 범위, 중복 없음)"""
    results = set()
    
    # ① 기본수: 생명수 그 자체
    results.add(lp)
    
    # ② 배수: 생명수 × 5
    multiple = lp * 5
    if multiple > 45:
        multiple = ((multiple - 1) % 45) + 1
    results.add(multiple)
    
    # ③ 보완수: (생명수 + 생명수²) mod 45 + 1
    complement = ((lp + lp * lp) % 45) + 1
    while complement in results:
        complement = (complement % 45) + 1
    results.add(complement)
    
    return sorted(results)


def calculate_lucky_numbers(mmdd: str) -> list:
    """월일 4자리 → 행운수 3개"""
    lp = get_life_path_number(mmdd)
    return get_lucky_numbers_from_life_path(lp)


def calculate_all_lucky_numbers(birthday_list: list) -> list:
    """여러 명 생일 → 통합 행운수 (중복 제거, 잘못된 월일은 건너뜀)."""
    all_nums = set()
    for mmdd in birthday_list:
        try:
            for n in calculate_lucky_numbers(mmdd):
                all_nums.add(n)
        except ValueError:
            continue
    return sorted(all_nums)


# 생명수별 의미
LIFE_PATH_MEANINGS = {
    1: "리더십, 독립, 창조",
    2: "협력, 균형, 조화",
    3: "표현, 창의, 소통",
    4: "안정, 근면, 질서",
    5: "자유, 변화, 모험",
    6: "책임, 사랑, 가정",
    7: "탐구, 지혜, 직관",
    8: "성공, 풍요, 권위",
    9: "봉사, 완성, 인류애",
}
