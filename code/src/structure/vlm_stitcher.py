# src/structure/vlm_stitcher.py
import argparse, json
from pathlib import Path
from utils.io import ensure_dir, write_json

def vlm_to_docjson_and_md(vlm_json_path, doc_id, out_dir):
    out_dir = Path(out_dir)
    ensure_dir(out_dir)
    with open(vlm_json_path, 'r', encoding='utf-8') as f:
        vlm = json.load(f)
    # Assume vlm is a dict with 'reads' or a list of region dicts
    regions = vlm.get('reads') if isinstance(vlm, dict) and 'reads' in vlm else vlm
    if not isinstance(regions, list):
        raise ValueError('VLM output not a list of regions')
    blocks = []
    md_lines = []
    for region in regions:
        # Example: {'type': 'heading', 'text': '...', 'level': 2, ...}
        typ = region.get('type', 'paragraph')
        text = region.get('text', '')
        conf = float(region.get('confidence', 1.0))
        block = {'type': typ, 'text_native': text, 'confidence': conf}
        if 'level' in region:
            block['level'] = region['level']
        blocks.append(block)
        # Markdown rendering
        if typ.startswith('heading'):
            level = int(region.get('level', 2))
            md_lines.append('#' * level + ' ' + text)
        elif typ == 'table' and 'markdown' in region:
            md_lines.append(region['markdown'])
        else:
            md_lines.append(text)
    # Write doc.json
    write_json({'doc_id': doc_id, 'blocks': blocks}, out_dir/'doc.json')
    # Write doc.md
    (out_dir/'doc.md').write_text('\n\n'.join(md_lines), encoding='utf-8')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--doc_id', required=True)
    ap.add_argument('--vlm_json', required=True)
    ap.add_argument('--out_dir', required=True)
    args = ap.parse_args()
    vlm_to_docjson_and_md(args.vlm_json, args.doc_id, args.out_dir)
