# AI 실수 기록

## 1. 확인하지 않은 의존성 우선순위로 배포 구조를 정함 (2026-10-27, Task 1)
- Claude가 한 것: Vercel 문서에서 `api/index.py`가 자동 감지 위치가 아님을 확인하고, `pyproject.toml`의 `tool.vercel.entrypoint`로 지정했다. 같은 파일에 pytest 설정만 넣고 의존성은 `requirements.txt`에 두었다.
- 무엇이 틀렸나: `pyproject.toml`이 있으면 Vercel이 `requirements.txt` 대신 그 파일로 의존성을 설치한다. 문서에 두 파일이 함께 있을 때의 우선순위는 없었는데, 확인하지 않은 채 함께 둬도 된다고 가정했다. 또 `api/` 폴더가 파일 기반 함수로 잡혀 `/api/health`가 404였다.
- 어떻게 발견했나: 미리보기 배포에서 `/api/health` 404 → `vercel inspect --logs`의 `Installing required dependencies from pyproject.toml...`와 빌드 결과 `λ api/index`
- 어떻게 고쳤나: 진입 파일을 루트 `index.py`(자동 감지 위치)로 옮기고 `pyproject.toml`을 없앴다. pytest 설정은 `pytest.ini`로 옮겼다. 진입점 테스트(`tests/web/test_web_entry.py`)를 먼저 추가했다.
- 재발 방지: `CLAUDE.md`에 "`pyproject.toml`을 만들지 않는다" 규칙과 이유를 적었다. 문서에 없는 동작은 배포로 확인하기 전까지 결정기록에 "잠정"으로 둔다.
