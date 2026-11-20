"""MinerU 4.x 쪽별 마크다운 추출: python run_mineru.py <PDF> <출력 json> [tier]
CPU 고정은 환경변수 MINERU_MODEL_ONNX_DEVICE=cpu (GPU 실행은 gpu)로 한다.
쪽별 마크다운: parse() 결과의 middle_json.pages(page_idx 0부터)를 한 쪽씩 담은 사본을 render_markdown으로 렌더링한다."""
import copy, json, sys, time
from mineru.parser import parse
from mineru.render import render_markdown
from mineru.types import MiddleJson

def main():
    pdf, out = sys.argv[1], sys.argv[2]
    tier = sys.argv[3] if len(sys.argv) > 3 else "standard"
    ocr_mode = sys.argv[4] if len(sys.argv) > 4 else "auto"
    t = time.time()
    result = parse(pdf, tier=tier, ocr_mode=ocr_mode)  # Fable 계획 Task 3: ocr_mode만 인자로, 나머지 기본, image_analysis=True, 전체 쪽
    sec = time.time() - t
    d = result.to_dict()
    pages = d["pages"]
    idx = [p["page_idx"] for p in pages]
    res = []
    for p in pages:
        one = copy.deepcopy(d)
        one["pages"] = [p]
        res.append({"page": p["page_idx"] + 1, "markdown": render_markdown(MiddleJson.from_dict(one))})
    # 쪽 번호가 0..n-1 연속인지 확인(PDF 쪽 순서와 같은지)
    assert idx == list(range(len(idx))), f"page_idx mismatch {idx[:5]}"
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"pages={len(res)} seconds={sec:.1f} chars_nospace={sum(len(''.join(r['markdown'].split())) for r in res)}")


if __name__ == "__main__":  # PDF 렌더 작업 프로세스가 spawn으로 이 파일을 다시 불러오므로 필요
    main()
