# AI 실수 기록

## 1. 확인하지 않은 의존성 우선순위로 배포 구조를 정함 (2026-10-27, Task 1)
- Claude가 한 것: Vercel 문서에서 `api/index.py`가 자동 감지 위치가 아님을 확인하고, `pyproject.toml`의 `tool.vercel.entrypoint`로 지정했다. 같은 파일에 pytest 설정만 넣고 의존성은 `requirements.txt`에 두었다.
- 무엇이 틀렸나: `pyproject.toml`이 있으면 Vercel이 `requirements.txt` 대신 그 파일로 의존성을 설치한다. 문서에 두 파일이 함께 있을 때의 우선순위는 없었는데, 확인하지 않은 채 함께 둬도 된다고 가정했다. 또 `api/` 폴더가 파일 기반 함수로 잡혀 `/api/health`가 404였다.
- 어떻게 발견했나: 미리보기 배포에서 `/api/health` 404 → `vercel inspect --logs`의 `Installing required dependencies from pyproject.toml...`와 빌드 결과 `λ api/index`
- 어떻게 고쳤나: 진입 파일을 루트 `index.py`(자동 감지 위치)로 옮기고 `pyproject.toml`을 없앴다. pytest 설정은 `pytest.ini`로 옮겼다. 진입점 테스트(`tests/web/test_web_entry.py`)를 먼저 추가했다.
- 재발 방지: `CLAUDE.md`에 "`pyproject.toml`을 만들지 않는다" 규칙과 이유를 적었다. 문서에 없는 동작은 배포로 확인하기 전까지 결정기록에 "잠정"으로 둔다.

## 2. 바닥글 수치를 일부만 세서 보고함 (2026-10-28, Task 6 Step 1-3)
- Claude가 한 것: 채팅의 Claude가 PDF 도구를 재비교하면서, pypdfium2로 바꾸면 삼성 설명서의 바닥글이 "79줄 → 1줄"로 준다고 보고했다. 이 수치는 기획서 3.2와 계획 Task 6 Step 1-3 참고값에 들어갔다.
- 무엇이 틀렸나: 반복 글자 줄(`UUnnttiittlleedd…`처럼 글자가 두 번씩 나오는 줄)만 센 값이었다. pypdfium2에서는 바닥글이 깨지지 않은 형태(`Untitled-1 1 2026-02-26 10:06:26`)로 바뀌어 **쪽마다 1줄, 80줄**이 그대로 남는다. 보고대로라면 `clean_text()`가 거의 필요 없어 보이지만, 실제로는 계속 필요하다.
- 어떻게 발견했나: Claude Code가 사용자 컴퓨터에서 같은 기준으로 재측정했다(반복 글자 줄 0줄, `Untitled` 줄 80줄). 결과를 보고와 대조해서 차이를 찾았다.
- 어떻게 고쳤나:
  - 결정기록 016 "수정" 절과 부록에 재측정 값을 적었다.
  - 기획서 v0.20에서 바닥글 수치를 정정했다.
  - `clean_text()`가 정상 글자 바닥글도 거르게 한다(Task 6).
- 재발 방지:
  - 잡음은 "깨진 형태"와 "남아 있는 줄 전체"를 따로 센다.
  - 채팅 환경에서 잰 값은 사용자 컴퓨터에서 같은 스크립트로 재확인한 뒤에 확정한다. 재현 스크립트는 `experiments/extract_compare/`에 둔다.
