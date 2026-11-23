# -*- coding: utf-8 -*-
"""生成真实场景试听页：自动扫描各阶段产物 → spec.json → 调用 build_prosody_page.py

用法:
  python -u build_scene_spec.py castle1
"""
import json
import os
import subprocess
import sys

import soundfile as sf

sys.path.insert(0, r'G:/_setup')

OUT = r'E:/tts-models/out/scene'
PAGE = r'E:/tts-models/out/scene/listen_scene.html'
REF_A = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0018112640_0018378240.wav'
REF_B = r'G:/GPT-SoVITS/_dataset/sliced/wonder_train.wav_0019802560_0020009920.wav'

TAG = sys.argv[1] if len(sys.argv) > 1 else 'castle1'
TEXT_FILE = sys.argv[2] if len(sys.argv) > 2 else r'G:/_setup/scene_castle1.txt'


def dur(p):
    return sf.info(p).duration if os.path.exists(p) else 0.0


def main():
    text = open(TEXT_FILE, encoding='utf-8').read().strip()
    nw = len(text.split())
    wav = lambda n: os.path.join(OUT, '%s_%s.wav' % (TAG, n))

    pj = os.path.join(OUT, '%s_pauses.json' % TAG)
    npause = 0
    ptxt = []
    if os.path.exists(pj):
        pl = json.load(open(pj, encoding='utf-8'))
        npause = len(pl)
        ptxt = ['%s %.2fs' % (x['word'].strip(), x['target']) for x in pl[:6]]

    stages = [
        ('① 生成 · 逐句拼接（无后处理）', wav('joined'), 'raw', ''),
        ('② + 标点停顿注入（强度 1.0）', wav('pause'), '+停顿', ''),
        ('③ + F0 夸张 k=1.6（Praat）', wav('ex'), '+韵律', ''),
        ('④ + 高频补偿 EQ（最终）', wav('final'), '★ 最终', 'best'),
    ]
    items = []
    for label, p, tag, cls in stages:
        if not os.path.exists(p):
            continue
        d = dur(p)
        note = '%.2fs · %d 词 · 约 %.0f wpm' % (d, nw, nw / (d / 60.0))
        if npause and 'pause' in p:
            note += ' · 插入 %d 处停顿：%s' % (npause, '、'.join(ptxt))
        items.append(dict(label=label, wav=p, tag=tag, cls=cls, note=note))

    strengths = [
        ('停顿 0.7×（逗号 0.81s / 句号 1.09s）', wav('p07_final'), '0.7×', ''),
        ('停顿 1.0×（逗号 1.16s / 句号 1.56s）', wav('final'), '1.0×', 'best'),
        ('停顿 1.3×（逗号 1.51s / 句号 2.03s）', wav('p13_final'), '1.3×', ''),
    ]
    sitems = []
    for label, p, tag, cls in strengths:
        if not os.path.exists(p):
            continue
        d = dur(p)
        sitems.append(dict(label=label, wav=p, tag=tag, cls=cls,
                           note='%.2fs · 约 %.0f wpm' % (d, nw / (d / 60.0))))

    spec = {
        'title': '真实场景 · 马修的声音读《I\u2019m the King of the Castle》',
        'head': ('原文（Susan Hill《I\u2019m the King of the Castle》第 1 章）：<br>'
                 '<code>%s</code><br><br>'
                 '这是<b>没有 donor 录音</b>时的完整链路 —— 也就是你实际读书时会走的流程：'
                 '逐句生成 → 按语料统计的<b>标点停顿原型</b>注入停顿 → F0 夸张 → 高频补偿。'
                 '按顺序听，能听出每一步的贡献。' % text.replace('&', '&amp;').replace('<', '&lt;')),
        'hint': ('<b>听什么：</b>① → ④ 逐步加上后处理。重点听 <b>②</b>（逗号/句号处是否出现了那种'
                 '「顿一下」的分量感）和 <b>④</b>（整体是否更像公开朗读）。<br>'
                 '停顿原型来自对马修 21.4 分钟原声的统计：<b>逗号后中位 1.16s、句号后中位 1.56s</b>'
                 '（普通朗读只有 0.3–0.5s / 0.6–0.8s）。'),
        'groups': [
            {'name': '目标音色（马修原声 · Wonder）',
             'note': '这是训练与模仿的源头。注意他的语速很慢、句间留白很长。',
             'items': [
                 {'label': '原声 · called Sirius…（参考音频来源）', 'wav': REF_A,
                  'cls': 'real', 'tag': '真人'},
                 {'label': '原声 · Right here, right now…（含两处逗号停顿）', 'wav': REF_B,
                  'cls': 'real', 'tag': '真人'},
             ]},
            {'name': '真实场景 · 城堡之王 第 1 章（%d 词）' % nw,
             'note': '无 donor 录音，全靠「语料停顿原型 + 韵律后处理」。',
             'items': items},
            {'name': '停顿强度对比（马修原声实测：逗号 1.16s / 句号 1.56s）',
             'note': '同一条音频，只改停顿长度。听哪个最像「公开朗读」而不是「念稿」。',
             'items': sitems},
        ],
    }

    sp = os.path.join(OUT, '%s_spec.json' % TAG)
    json.dump(spec, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('spec 写出 %s（%d 条音频）' % (sp, len(items) + 2))
    subprocess.run([sys.executable, '-u', r'G:/_setup/build_prosody_page.py', sp, PAGE], check=True)
    print('页面:', PAGE)


if __name__ == '__main__':
    main()
