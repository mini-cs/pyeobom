#!/usr/bin/env bash
# 운영 첫 화면을 Lighthouse 모바일 기본 설정으로 3회 재고 중앙값을 출력한다(AI 비용 없음).
# 질문으로 서버를 미리 깨우지 않는다: 첫 화면은 CDN의 정적 파일이라 함수 대기와 무관하다.
set -euo pipefail
URL="${1:-https://pyeobom.vercel.app}"
mkdir -p measure/out
for n in 1 2 3; do
  npx -y lighthouse "$URL" --output=json --output-path="measure/out/lh-$n.json" --quiet --chrome-flags="--headless"
done
python -m measure.lighthouse measure/out/lh-1.json measure/out/lh-2.json measure/out/lh-3.json
