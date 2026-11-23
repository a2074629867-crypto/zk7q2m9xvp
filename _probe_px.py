# -*- coding: utf-8 -*-
"""像素级验证：节点间隙里到底有没有连线被画出来。"""
import json
import sys

from playwright.sync_api import sync_playwright
from PIL import Image

OUT = 'G:/_setup/_v5_narr.png'

JS = '''
() => {
  const v = document.querySelector('.view.on');
  const cv = v.querySelector('.canvas');
  const cb = cv.getBoundingClientRect();
  const g = id => {
    const e = v.querySelector('[data-id="'+id+'"]');
    const r = e.getBoundingClientRect();
    return {l:r.left-cb.left, t:r.top-cb.top, r:r.right-cb.left, b:r.bottom-cb.top};
  };
  const svg = cv.querySelector('.wires');
  const cs = getComputedStyle(svg);
  const p0 = cv.querySelector('.wires path[marker-end]');
  const ps = p0 ? getComputedStyle(p0) : null;
  return {
    w1: g('w1'), w2: g('w2'), r1: g('r1'), r2: g('r2'),
    svgBox: (()=>{const r=svg.getBoundingClientRect();return {l:r.left-cb.left,t:r.top-cb.top,w:r.width,h:r.height};})(),
    svgZ: cs.zIndex, svgPos: cs.position,
    pathStroke: ps ? ps.stroke : null,
    pathOpacity: ps ? ps.opacity : null,
    pathWidth: ps ? ps.strokeWidth : null,
    nPaths: cv.querySelectorAll('.wires path[marker-end]').length
  };
}
'''


def probe(img, name, rect_a, rect_b):
    """在 A 的右边缘与 B 的左边缘之间的竖直带里找非背景像素。"""
    x0 = int(rect_a['r']) + 1
    x1 = int(rect_b['l']) - 1
    y0 = int(min(rect_a['t'], rect_b['t']))
    y1 = int(max(rect_a['b'], rect_b['b']))
    if x1 <= x0 or y1 <= y0:
        print('  %-8s 间隙无效 x%d..%d' % (name, x0, x1))
        return
    crop = img.crop((x0, y0, x1, y1)).convert('RGB')
    px = list(crop.getdata())
    bg = (13, 17, 23)
    hit = sum(1 for c in px
              if abs(c[0] - bg[0]) + abs(c[1] - bg[1]) + abs(c[2] - bg[2]) > 24)
    print('  %-8s 间隙 %dx%d = %d px，非背景 %d px (%.1f%%)'
          % (name, x1 - x0, y1 - y0, len(px), hit, 100.0 * hit / max(len(px), 1)))


with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge')
    pg = b.new_page(viewport={'width': 1600, 'height': 1600})
    pg.goto('file:///G:/_setup/loop_map_v5.html?v=5')
    pg.wait_for_timeout(1600)
    info = pg.evaluate(JS)
    pg.locator('.view.on .canvas').screenshot(path=OUT)
    b.close()

print('svg z-index =', info['svgZ'], '| position =', info['svgPos'])
print('svg box     =', {k: round(v) for k, v in info['svgBox'].items()})
print('path stroke =', info['pathStroke'], '| opacity =', info['pathOpacity'],
      '| width =', info['pathWidth'], '| 共', info['nPaths'], '条')
print()
img = Image.open(OUT)
print('截图尺寸', img.size)
probe(img, 'w1→w2', info['w1'], info['w2'])
probe(img, 'r1→r2', info['r1'], info['r2'])
print('→', OUT)
