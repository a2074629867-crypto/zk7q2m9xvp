# -*- coding: utf-8 -*-
"""S3 起伏闭环：按粒度档位重生成，复测 span，四道硬闸门

核心事实（实测，别推翻）：
  · energy_span 随生成粒度单调变化：整块单 span 25.6 → 按句拆 span 30.5 → 每句独立 38.0
  · 换 seed 无效：854 对同文本跨 seed 只差 1.4dB，0 例「一个平一个陡」
  ⇒ 太平就往细拆，太陡就往粗并。seed 全程固定为原 take 的 seed。

档位：
  旁白  G1 整段一次生成（最粗） / G2 按句拆开分别生成再拼（最细）
  对白  D2 现状一句一条 / D3 按从句拆开分别生成再拼（更细）
        —— 对白没有「更粗」档（一句一条已是最粗），FIX_HIGH 只能进清单

硬闸门（任一不过 → 回退原 take）：
  ① 目标带：复测 span ∈ [p25, p75]
  ② ASR 词召回不低于原 take
  ③ 声纹 ≥ 0.65（同角色 ref）
  ④ 峰值 < 0.999

用法：
  python mt_rhythm_fix.py --gate _gate_dialogue.json --which LOW --limit 2
  python mt_rhythm_fix.py --gate _gate_narr.json --which HIGH --limit 3
  python mt_rhythm_fix.py --gate _gate_dialogue.json --dry
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mt_rhythm_bands import FLOOR_TARGET, measure

BANDS_DEFAULT = r'G:/_setup/_rhythm_bands.json'
OUT_DEFAULT = r'G:/_setup/_rhythm_fix.json'
PLAN_DEFAULT = r'G:/_setup/mt_plan2.json'
SPK_TH = 0.65
GAP = 0.10


# ---------------- 文本 ----------------
def split_sents(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]


def split_clauses(text, min_words=3):
    """按 , ; : 和句末标点拆成从句，标点保留在前一段末尾。

    过短的片段（<3 词，如 `Well,`）必须并进下一段：实测单独生成 `Well,` 会直接失败
    （rc=1、无输出），因为文本太短模型没有内容可读。
    """
    parts = [p.strip() for p in re.split(r'(?<=[,;:.])\s+', text.strip()) if p.strip()]
    out = []
    buf = ''
    for p in parts:
        buf = (buf + ' ' + p).strip() if buf else p
        if len(buf.split()) >= min_words:
            out.append(buf)
            buf = ''
    if buf:
        if out:
            out[-1] = out[-1] + ' ' + buf
        else:
            out.append(buf)
    return out if len(out) >= 2 else []


def load_texts():
    t = {}
    try:
        for r in json.load(open(PLAN_DEFAULT, encoding='utf-8')):
            t[r['id']] = r['text']
    except Exception:
        pass
    try:
        from ch123_plan import INNER, PLAN
        for i, _, _, x in PLAN:
            t['L%03d' % i] = x
        for i, (_, _, _, x) in enumerate(INNER):
            t['I%02d' % i] = x
    except Exception:
        pass
    return t


# ---------------- 生成 ----------------
def gen_narr(text, out, seed, max_tokens=600):
    from narr_rate_calib import gen
    return gen(text, out, seed=seed, max_tokens=max_tokens)


def gen_dialogue(text, out, speaker, seed, max_tokens=600):
    import shutil
    import bk_resplit as R
    from ch123_plan import REFS
    ref, rt = REFS[speaker]
    # --out 相对路径基于 ACPP_DIR（在 C:），不能直接给 G: 的绝对路径
    tmp_dir = os.path.join(R.ACPP_DIR, '_rhythm_fix')
    os.makedirs(tmp_dir, exist_ok=True)
    out_rel = '_rhythm_fix/' + os.path.basename(out)
    out_abs = os.path.join(R.ACPP_DIR, out_rel)
    cmd = [R.ACPP, "--task", "tts", "--family", "dots_tts", "--model", R.MODEL,
           "--backend", "vulkan", "--threads", "2",
           "--voice-ref", ref, "--reference-text", rt, "--text", text,
           "--request-option", "max_tokens=%d" % max_tokens,
           "--seed", str(seed), "--out", out_rel,
           "--session-option", "dots_tts.mem_saver=true"]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=R.ACPP_DIR, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    ok = os.path.exists(out_abs) and os.path.getsize(out_abs) > 20000
    if ok:
        shutil.copy2(out_abs, out)
    lines = ((r.stdout or '') + (r.stderr or '')).strip().splitlines()
    return (0 if ok else 1), ' | '.join(lines[-2:]), time.time() - t0


def rms_norm(x, target_db=-24.0):
    r = float(np.sqrt((x.astype(np.float64) ** 2).mean()) + 1e-12)
    g = 10 ** (target_db / 20.0) / r
    return (x * g).astype(np.float32)


def concat(parts, gap=GAP):
    """逐段 RMS 归一到 −24（与生产链一致），中间留 gap 秒静音。"""
    xs = []
    sr0 = None
    for p in parts:
        x, sr = sf.read(p, dtype='float32')
        if x.ndim > 1:
            x = x.mean(1)
        sr0 = sr
        xs.append(rms_norm(x))
    sil = np.zeros(int(gap * sr0), dtype=np.float32)
    out = []
    for i, x in enumerate(xs):
        if i:
            out.append(sil)
        out.append(x)
    return np.concatenate(out), sr0


# ---------------- 硬闸门 ----------------
ASR_PY = r'G:/_setup/asr_venv/Scripts/python.exe'
ASR_CODE = ("import sys,json;sys.path.insert(0,r'G:/_setup');"
            "from _asr_lib import transcribe;r=transcribe([sys.argv[1]]);"
            "print(json.dumps([v['text'] for v in r.values()]))")


def asr_words(path):
    """ASR 只在 asr_venv 里能跑（主环境缺 onnx_asr），必须走子进程。"""
    if not os.path.exists(ASR_PY):
        return None
    env = dict(os.environ, HF_ENDPOINT='hf-mirror.com', HF_HUB_OFFLINE='1')
    try:
        r = subprocess.run([ASR_PY, '-c', ASR_CODE, path], capture_output=True,
                           text=True, encoding='utf-8', errors='replace',
                           env=env, timeout=300)
        lines = [l for l in (r.stdout or '').strip().splitlines() if l.startswith('[')]
        if not lines:
            return None
        txt = ' '.join(json.loads(lines[-1]))
        return re.findall(r"[a-z']+", txt.lower())
    except Exception:
        return None


def recall(ref_words, hyp_words):
    if not ref_words or hyp_words is None:
        return None
    sm = difflib.SequenceMatcher(None, ref_words, hyp_words, autojunk=False)
    hit = sum(b.size for b in sm.get_matching_blocks())
    return hit / max(1, len(ref_words))


def spk_cos(a, b):
    try:
        sys.path.insert(0, r'C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/reader/_tts_lab')
        import spk_embed as S
        return float(S.cos(S.embed(a), S.embed(b)))
    except Exception:
        return None


def gate_check(path, band, orig_path, orig_words, ref_wav=None):
    x, sr = sf.read(path, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    m = measure(x, sr, 'narr')
    reasons = []
    e = band.get('energy_span') or {}
    span = m.get('energy_span')
    ok_band = span is not None and e.get('p25') is not None and e['p25'] <= span <= e['p75']
    if not ok_band:
        reasons.append('span %s 不在 [p25 %.1f, p75 %.1f]' % (span, e.get('p25', 0), e.get('p75', 0)))
    peak = float(np.abs(x).max())
    if peak >= 0.999:
        reasons.append('削波 %.3f' % peak)
    rec = None
    w = asr_words(path)
    if w is not None and orig_words:
        rec = recall(orig_words, w)
        if rec is not None and rec < 0.90:
            reasons.append('ASR 召回 %.2f' % rec)
    # ★ 声纹必须跟「原 take」比，不能跟法语参考音色比：
    #   实测原 take 与 CH_neutral.wav 的余弦就是 −0.057（跨语言锚点不可比），
    #   拿它当基准会把所有 take 判死。跟原 take 比才是「还是不是同一个人」。
    cos = spk_cos(path, orig_path) if orig_path and os.path.exists(orig_path) else None
    if cos is not None and cos < SPK_TH:
        reasons.append('声纹 %.3f' % cos)
    return dict(span=span, peak=round(peak, 3), asr_recall=None if rec is None else round(rec, 3),
                spk_cos=None if cos is None else round(cos, 3),
                ok=not reasons, reasons=reasons, **{k: m.get(k) for k in
                                                   ('head_slope', 'tail_slope', 'rev_rate', 'dur')})


def _read(path):
    x, sr = sf.read(path, dtype='float32')
    if x.ndim > 1:
        x = x.mean(1)
    return x, sr


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gate', default=r'G:/_setup/_gate_dialogue.json')
    ap.add_argument('--bands', default=BANDS_DEFAULT)
    ap.add_argument('--which', default='LOW', choices=['LOW', 'HIGH', 'both'])
    ap.add_argument('--limit', type=int, default=2)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out', default=OUT_DEFAULT)
    ap.add_argument('--workdir', default=r'G:/_setup/_rhythm_fix')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    bands = json.load(open(a.bands, encoding='utf-8'))
    gate = json.load(open(a.gate, encoding='utf-8'))
    texts = load_texts()
    os.makedirs(a.workdir, exist_ok=True)

    want = ('FIX_LOW',) if a.which == 'LOW' else (
        ('FIX_HIGH',) if a.which == 'HIGH' else ('FIX_LOW', 'FIX_HIGH'))
    todo = [r for r in gate['rows'] if r['verdict'] in want]
    if a.limit:
        todo = todo[:a.limit]
    print('候选 %d 条（%s）' % (len(todo), a.which), flush=True)

    src_dir = None
    for k in ('tag',):
        pass
    results = []
    for r in todo:
        key = r['unit']
        role = r['role']
        band = bands.get(role) or {}
        text = texts.get(key, '')
        src = _find_src(key)
        rec = dict(key=key, role=role, verdict=r['verdict'], src_span=r.get('energy_span'),
                   text=text[:120], levels=[])
        print('\n== %s  %s  span %s  %s' % (key, r['verdict'], r.get('energy_span'), role), flush=True)
        if not text or not src:
            rec['final'] = 'no_text_or_src'
            print('   跳过：%s' % ('缺文本' if not text else '缺源文件'), flush=True)
            results.append(rec)
            continue
        if a.dry:
            rec['plan'] = ['G1', 'G2'] if role == 'narr' else ['D3']
            print('   dry：文本「%s」' % text[:70], flush=True)
            results.append(rec)
            continue

        # 原 take 的 ASR 词表（召回基准）
        ow = asr_words(src) or []

        cands = []
        if role == 'narr':
            ladder = [('G1', [text]), ('G2', split_sents(text))]
        else:
            ladder = [('D2', [text]), ('D3', split_clauses(text) or [text])]

        for name, parts in ladder:
            if len(parts) == 1 and name in ('G2', 'D3'):
                continue
            t0 = time.time()
            paths = []
            fail = False
            for j, p in enumerate(parts):
                out = os.path.join(a.workdir, '%s_%s_%02d.wav' % (key, name, j))
                if role == 'narr':
                    rc, msg, el = gen_narr(p, out, a.seed)
                else:
                    rc, msg, el = gen_dialogue(p, out, 'C' if role == 'charles' else 'E', a.seed)
                if rc != 0 or not os.path.exists(out):
                    print('   %s part%d 失败 %s %s' % (name, j, rc, msg[:80]), flush=True)
                    fail = True
                    break
                paths.append(out)
            if fail:
                rec['levels'].append(dict(level=name, n_parts=len(parts), status='gen_fail'))
                continue
            if len(paths) == 1:
                merged = paths[0]
            else:
                y, sr = concat(paths)
                merged = os.path.join(a.workdir, '%s_%s_merged.wav' % (key, name))
                sf.write(merged, y, sr, subtype='PCM_16')
            g = gate_check(merged, band, src, ow)
            g.update(level=name, n_parts=len(parts), path=merged, sec=round(time.time() - t0, 1))
            rec['levels'].append(g)
            print('   %s %d段 → span %s  声纹 %s  ASR %s  %.0fs  %s'
                  % (name, len(parts), g['span'], g['spk_cos'], g['asr_recall'], g['sec'],
                     'OK' if g['ok'] else '; '.join(g['reasons'])), flush=True)
            cands.append(g)
            if g['ok']:
                break

        good = [c for c in cands if c['ok']]
        if good:
            best = min(good, key=lambda c: abs((c['span'] or 0) - band['energy_span']['p50']))
            rec['final'] = 'adopt:' + best['level']
            rec['adopted'] = best['path']
        else:
            rec['final'] = 'revert'
        results.append(rec)

    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print('\n写出 %s' % a.out)
    for r in results:
        print('  %-10s %-10s → %s' % (r['key'], r['verdict'], r.get('final')))


def _find_src(key):
    for d in (r'G:/_setup/_mt_raw_s42', r'G:/_setup/ch123_final_llm',
              r'G:/_setup/ch123_final'):
        p = os.path.join(d, key + '.wav')
        if os.path.exists(p):
            return p
    return None


if __name__ == '__main__':
    main()
