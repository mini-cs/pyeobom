"""DeepEval 지표 3개(Faithfulness, Answer Relevancy, Contextual Relevancy)로 1차 답을 채점한다(보조 지표, AI 비용 있음).

사용법: python -m measure.run_deepeval <평가 결과 CSV> <근거 본문 JSON> [--model gpt-5-nano] [--limit N]
- 실행 전에 docs/평가/baseline-v1.md 비용 장부에 예상 비용을 적고 check_budget을 통과해야 한다.
- DeepEval 텔레메트리는 끄고(DEEPEVAL_TELEMETRY_OPT_OUT=1), Confident AI에는 로그인·업로드하지 않는다.
- 판정 이유(reason)는 설명서 문장을 담을 수 있어 measure/out/에만 저장한다(저장소에 넣지 않음).
"""
import os

os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"  # deepeval을 불러오기 전에 끈다

import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import statistics  # noqa: E402
from pathlib import Path  # noqa: E402

from ingest.__main__ import load_env  # noqa: E402
from measure.deepeval_cases import build_cases  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
METRICS = ("faithfulness", "answer_relevancy", "contextual_relevancy")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m measure.run_deepeval")
    parser.add_argument("csv")
    parser.add_argument("contexts")
    parser.add_argument("--model", default="gpt-5-nano")
    parser.add_argument("--limit", type=int, default=None, help="앞에서 N문항만(비용 확인용)")
    args = parser.parse_args()
    load_env()

    from deepeval.metrics import AnswerRelevancyMetric, ContextualRelevancyMetric, FaithfulnessMetric
    from deepeval.test_case import LLMTestCase

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    contexts = json.loads(Path(args.contexts).read_text(encoding="utf-8"))
    cases = build_cases(rows, contexts)[: args.limit]

    results, total_cost = [], 0.0
    for case in cases:
        test_case = LLMTestCase(input=case["input"], actual_output=case["actual_output"],
                                retrieval_context=case["retrieval_context"])
        result = {"id": case["id"]}
        for name, metric in zip(METRICS, (FaithfulnessMetric(model=args.model), AnswerRelevancyMetric(model=args.model),
                                          ContextualRelevancyMetric(model=args.model))):
            metric.measure(test_case)
            result[name], result[f"{name}_reason"] = metric.score, metric.reason
            total_cost += metric.evaluation_cost or 0.0
        results.append(result)
        print(case["id"], " ".join(f"{m}={result[m]:.2f}" for m in METRICS), flush=True)

    OUT.mkdir(exist_ok=True)
    label = Path(args.csv).stem
    (OUT / f"deepeval-{label}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    means = {m: round(statistics.mean(r[m] for r in results), 3) for m in METRICS}
    print(json.dumps({"cases": len(results), "model": args.model, "mean": means, "cost_usd": round(total_cost, 5)}))


if __name__ == "__main__":
    main()
