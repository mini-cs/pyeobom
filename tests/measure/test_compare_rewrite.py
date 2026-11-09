import pytest

from measure.compare_rewrite import needs_rewrite, shorten_history


@pytest.mark.parametrize("question", [
    "그건 얼마나 자주 해야 해요?", "그 거름망은 어디에 있어요?", "그거 켜 두면 전기세는?", "그래도 계속 뜨면 어떻게 해요?",
    "탈수만 하고 싶을 땐요?", "덜 마르면요?", "건조 중에도요?", "최대 몇 kg?", "이건 왜 그래요?",
])
def test_needs_rewrite_true(question):
    assert needs_rewrite(question)


@pytest.mark.parametrize("question", [
    "탈수할 때 세탁기가 엄청 흔들리고 시끄러워요", "에어컨에서 쾨쾨한 냄새가 나요", "세탁조 청소는 어떻게 해요?",
    "이불도 빨 수 있어요? 어떤 코스로 해요?",  # '이불'의 '이'는 가리키는 말이 아님
    "그릴 청소는 어떻게 해요?",  # '그릴'의 '그'도 아님
])
def test_needs_rewrite_false(question):
    assert not needs_rewrite(question)


def test_shorten_history_keeps_last_turn_and_200_chars():
    history = [{"question": "첫 질문", "answer": "가" * 50}, {"question": "직전 질문", "answer": "나" * 300}]
    assert shorten_history(history) == [{"question": "직전 질문", "answer": "나" * 200}]
    assert shorten_history([]) == []
