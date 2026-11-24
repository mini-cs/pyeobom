"""2차 모델 추가 시간 기록지: 읽기 검사·합계·개선 판정(설계 9.3-2·3·6)."""
import pytest

from evaluation.phase2_timelog import KINDS, improved, read_timelog, summarize

HEAD = "step,kind,start,end,note\n"


def write(tmp_path, body):
    path = tmp_path / "timelog.csv"
    path.write_text(HEAD + body, encoding="utf-8")
    return str(path)


def test_summarize_excludes_question_writing_judging_deploy_wait(tmp_path):
    # 사람 10분 + 기다림 5분 + 질문 쓰기 40분 + 판정 15분 + 배포 대기 3분 + 멈춤 30분
    path = write(tmp_path,
                 "json 항목,사람,2026-11-24 13:00,2026-11-24 13:10,\n"
                 "적재,기다림,2026-11-24 13:10,2026-11-24 13:15,\n"
                 "확인 질문,질문 쓰기,2026-11-24 13:15,2026-11-24 13:55,\n"
                 "쉼,멈춤,2026-11-24 13:55,2026-11-24 14:25,점심\n"
                 "판정,판정,2026-11-24 14:25,2026-11-24 14:40,\n"
                 "배포,배포 대기,2026-11-24 14:40,2026-11-24 14:43,\n")
    s = summarize(read_timelog(path))
    assert s["extra_work_min"] == 15 and s["total_min"] == 73 and s["paused_min"] == 30 and s["person_steps"] == 1
    assert s["excluded_min"] == 58


def test_improved_needs_half_time_and_fewer_person_steps():
    assert improved({"extra_work_min": 60, "person_steps": 9}, {"extra_work_min": 30, "person_steps": 8})
    assert not improved({"extra_work_min": 60, "person_steps": 9}, {"extra_work_min": 31, "person_steps": 3})
    assert not improved({"extra_work_min": 60, "person_steps": 9}, {"extra_work_min": 10, "person_steps": 9})


@pytest.mark.parametrize("body, line", [
    ("a,사람,2026-11-24 13:00,2026-11-24 13:10,\nb,사람,2026-11-24 13:05,2026-11-24 13:20,\n", 3),  # 겹침
    ("a,구경,2026-11-24 13:00,2026-11-24 13:10,\n", 2),  # 모르는 kind
    ("a,사람,2026-11-24 13:10,2026-11-24 13:00,\n", 2),  # 끝이 시작보다 앞
    ("a,사람,2026-11-24 13:10,2026-11-24 13:10,\n", 2),  # 0분
    ("a,사람,2026-11-24 13:00,오후 1시,\n", 2),  # 시각 형식
])
def test_read_timelog_rejects_overlap_unknown_kind_and_reversed_time(tmp_path, body, line):
    with pytest.raises(ValueError, match=f"{line}번째 줄"):
        read_timelog(write(tmp_path, body))


def test_read_timelog_rejects_missing_column(tmp_path):
    path = tmp_path / "timelog.csv"
    path.write_text("step,kind,start,end\na,사람,2026-11-24 13:00,2026-11-24 13:10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="note"):
        read_timelog(str(path))


def test_kinds_fixed():
    assert KINDS == ("사람", "기다림", "질문 쓰기", "판정", "배포 대기", "멈춤")
