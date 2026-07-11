# lucky_engine.py
def get_family_lucky_numbers(family_birthdays):
    """
    family_birthdays: [(m1, d1), (m2, d2), ...] 형태의 리스트
    return: 가족별로 도출된 행운수 리스트 (중복 제거)
    """
    lucky_pool = set()
    for m, d in family_birthdays:
        # 기존 오행 로직 활용 (나중에 수정 가능)
        base = (m * 100 + d) % 45
        lucky_pool.add(base if base != 0 else 45)
    return sorted(list(lucky_pool))