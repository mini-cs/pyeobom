from datetime import datetime

from measure.v17_count import count_new_responses, parse_kst, report

CUTOFF = datetime(2026, 11, 10, 13, 4, 4)
HEADER = "타임스탬프,동의,자취 경험,1. 가짜카드,2. 가짜카드,3. 가짜카드\n"


def _csv(tmp_path, rows):
    path = tmp_path / "r.csv"
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8-sig")
    return path


def test_parse_kst_noon_and_midnight():
    assert parse_kst("2026. 11. 10 오후 12:20:11") == datetime(2026, 11, 10, 12, 20, 11)
    assert parse_kst("2026. 11. 11 오전 12:05:00") == datetime(2026, 11, 11, 0, 5, 0)
    assert parse_kst("2026. 11. 10 오후 1:04:05") == datetime(2026, 11, 10, 13, 4, 5)


def test_counts_only_numbers(tmp_path, capsys):
    path = _csv(tmp_path, [
        "2026. 11. 09 오후 3:00:00,동의해요,예,가짜문장옛날,,",
        "2026. 11. 11 오전 12:10:00,동의해요,예,가짜문장개발,가짜문장확인,",
        "2026. 11. 11 오후 12:10:00,동의해요,예,,   ,가짜문장확인2",
        "2026. 11. 12 오전 10:00:00,동의 안 함,예,가짜문장거부,,",
    ])
    result = count_new_responses(path, CUTOFF, dev_cards={1}, test_cards={2})
    assert result == {"dev": 1, "test": 1, "other": 1, "blank": 3}
    report(path, CUTOFF, {1}, {2})
    assert "가짜문장" not in capsys.readouterr().out
