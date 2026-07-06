from collectors import (
    ai_final_candidates,
    trading_value_ranking,
    stop_high_low,
)


COLLECTORS = [
    ai_final_candidates,
    trading_value_ranking,
    stop_high_low,
]


def run_collector(module):
    print(f"===== {module.__name__} =====")

    try:
        path = module.main()
        print(f"OK: {path}")
        return True

    except Exception as error:
        print(f"ERROR: {module.__name__}: {error}")
        return False


def main():
    success_count = 0

    for collector in COLLECTORS:
        if run_collector(collector):
            success_count += 1

    print(f"完了: {success_count}/{len(COLLECTORS)} 件成功")


if __name__ == "__main__":
    main()