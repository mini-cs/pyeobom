"""Marker 쪽별 마크다운 추출: python run_marker.py <PDF> <출력 json> [cpu|cuda]
paginate_output=True: 쪽 사이에 "\n\n{N}" + "-"*48 + "\n\n" 구분 표시(N은 0부터)."""
import json, os, re, sys, time


def main():
    pdf, out = sys.argv[1], sys.argv[2]
    device = sys.argv[3] if len(sys.argv) > 3 else "cpu"
    os.environ["TORCH_DEVICE"] = device  # 장치 지정(기본 설정 밖: 환경 변수만)

    import pypdfium2
    from marker.config.parser import ConfigParser
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    n = len(pypdfium2.PdfDocument(pdf))
    cfg = ConfigParser({"paginate_output": True, "output_format": "markdown"})
    t = time.time()
    conv = PdfConverter(artifact_dict=create_model_dict(), config=cfg.generate_config_dict(),
                        processor_list=cfg.get_processors(), renderer=cfg.get_renderer())
    load = time.time() - t
    t = time.time()
    md = conv(pdf).markdown
    sec = time.time() - t

    sep = re.compile(r"\n\n\{(\d+)\}-{48}\n\n")
    parts = sep.split(md)  # [앞, 번호, 본문, 번호, 본문...]
    found = {}
    if parts[0].strip():  # 첫 쪽 앞에도 표시가 없을 수 있음
        found[-1] = parts[0]
    for i in range(1, len(parts), 2):
        found[int(parts[i])] = parts[i + 1]
    print("raw markers:", sorted(k for k in found)[:3], "...", len(found), "head:", repr(md[:60]))
    base = 0 if 0 in found else 1
    res = [{"page": p, "markdown": found.get(p - 1 + base, "")} for p in range(1, n + 1)]
    extra = set(found) - {p - 1 + base for p in range(1, n + 1)}
    assert not extra, f"unexpected page markers {extra}"
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"pages={n} markers={len(found)} base={base} load={load:.1f} seconds={sec:.1f} chars_nospace={sum(len(''.join(r['markdown'].split())) for r in res)}")


if __name__ == "__main__":  # Windows spawn(다중 프로세스) 때문에 필요
    main()
