# -*- coding: utf-8 -*-
import io

p = 'G:/_setup/loop_map_two.html'
s = io.open(p, encoding='utf-8').read()
orig = s

# 1) 画布顶部留出 header 高度
s = s.replace('.canvas{position:relative;width:1480px;margin:0 auto;padding:4px 70px 0 72px}',
              '.canvas{position:relative;width:1480px;margin:0 auto;padding:22px 70px 0 72px}')

# 2) 网格间距 17 → 30
s = s.replace('gap:17px;align-items:start', 'gap:30px;align-items:start')

# 3) 连线更粗更亮
s = s.replace("stroke:'1.45',", "stroke:'1.55',")
s = s.replace("opacity:'0.68',", "opacity:'0.95',")

# 4) 默认线色 dim2 → dim
s = s.replace("let d='', color=cssVar('--dim2'), mk='ad', dash='';",
              "let d='', color=cssVar('--dim'), mk='ad', dash='';")
s = s.replace("[['ad', cssVar('--dim2')], ['ao', cssVar('--ok')],",
              "[['ad', cssVar('--dim')], ['ao', cssVar('--ok')],")

# 5) 箭头稍大
s = s.replace("markerWidth:'5', markerHeight:'5'", "markerWidth:'6', markerHeight:'6'")

io.open(p, 'w', encoding='utf-8').write(s)

checks = {
    'padding:22px 70px': 'padding:22px 70px' in s,
    'gap:30px': 'gap:30px' in s,
    "opacity:'0.95'": "opacity:'0.95'" in s,
    "markerWidth:'6'": "markerWidth:'6'" in s,
    "color --dim": "color=cssVar('--dim')" in s,
}
print('changed:', s != orig)
for k, v in checks.items():
    print('  %-18s %s' % (k, v))
print('size', len(s))
