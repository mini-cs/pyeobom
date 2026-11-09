#!/usr/bin/env bash
# Promptfoo 실행(미리보기 전용). 사용법: PREVIEW_URL=<미리보기 주소> bash measure/run_promptfoo.sh eval|redteam
# - 실행 전에 docs/평가/baseline-v1.md 비용 장부에 예상 비용을 적고 check_budget을 통과해야 한다.
# - 키·보호 우회 값은 .env에서 읽는다(--env-file). 결과 공유·텔레메트리·원격 생성은 끈다. 결과는 measure/out/에만 둔다.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PREVIEW_URL:?PREVIEW_URL을 미리보기 주소로 지정}"
.venv/Scripts/python -c "import sys; from measure.load_common import assert_not_production; assert_not_production(sys.argv[1])" "$PREVIEW_URL"
export PREVIEW_URL PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_SHARING=1 PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true
mkdir -p measure/out
case "${1:-}" in
  eval) npx promptfoo@0.125.1 eval -c measure/promptfoo/promptfooconfig.yaml --env-file .env --no-cache --no-share -o measure/out/promptfoo-eval.json ;;
  redteam) npx promptfoo@0.125.1 redteam run -c measure/promptfoo/redteamconfig.yaml --env-file .env --no-cache --strict -o measure/out/promptfoo-redteam.yaml && npx promptfoo@0.125.1 export eval latest -o measure/out/promptfoo-redteam-results.json ;;
  *) echo "eval 또는 redteam" >&2; exit 2 ;;
esac
