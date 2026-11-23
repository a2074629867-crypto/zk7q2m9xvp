#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 RAG 外部记忆 —— 单文件实现，零外部服务。

通道：
  lex  : SQLite FTS5 (unicode61) + 中文 bigram 展开 + BM25
  vec  : bge-small-zh-v1.5 ONNX (512 维, CLS pooling, L2 归一)
融合：RRF (Reciprocal Rank Fusion)

用法：
  python rag.py index [--rebuild]        建/更新索引
  python rag.py search "查询" [-k 8] [-m hybrid|lex|vec]
  python rag.py get <id>                 看完整 chunk
  python rag.py stats
  python rag.py fact add -t 主题 -c 结论 [-e 证据] [-s 状态]
  python rag.py fact list [-t 关键词]
  python rag.py fact search "查询" [-k 5]
"""
import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "db", "rag.sqlite")
VEC = os.path.join(ROOT, "db", "vec.npy")
VECIDS = os.path.join(ROOT, "db", "vec_ids.npy")
FACTS = os.path.join(ROOT, "facts.jsonl")
CONF = os.path.join(ROOT, "sources.json")
MODEL_DIR = os.path.join(ROOT, "models", "bge-small-zh")

# bge 中文版官方检索指令前缀（只加在 query，不加在 doc）
BGE_Q_PREFIX = "为这个句子生成表示以用于检索相关文章："

DEFAULT_SOURCES = [
    {"path": "C:/Users/86178/WorkBuddy/2026-10-05-00-50-22/.workbuddy/memory",
     "glob": "*.md", "tag": "journal", "depth": 1},
    {"path": "G:/_setup", "glob": "*.md", "tag": "report", "depth": 1},
    {"path": "G:/_setup/emo_bench", "glob": "*.md", "tag": "report", "depth": 1},
    {"path": "C:/Users/86178/.workbuddy/skills/dots-tts-dubbing",
     "glob": "*.md", "tag": "skill", "depth": 1},
    {"path": "C:/Users/86178/.workbuddy/skills/local-machine-ops",
     "glob": "*.md", "tag": "skill", "depth": 1},
    {"path": "C:/Users/86178/.workbuddy/skills/project-rag",
     "glob": "*.md", "tag": "skill", "depth": 1},
    # 下载域（2026-11-08 建档）：路由 skill 本身必须可检索，否则「怎么下这个视频」
    # 只能落回报告正文，拿不到「先判断链路」这层分发逻辑。
    {"path": "C:/Users/86178/.workbuddy/skills/video-download-toolchain",
     "glob": "*.md", "tag": "skill", "depth": 1},
    {"path": "C:/Users/86178/.workbuddy/skills/chinese-subtitle-fetch",
     "glob": "*.md", "tag": "skill", "depth": 1},
    {"path": "C:/Users/86178/.workbuddy/skills/okru-video-download",
     "glob": "*.md", "tag": "skill", "depth": 1},
]

MIN_CHUNK = 180       # 小于这个字数就并到下一块
MAX_CHUNK = 900       # 超过就硬切
OVERLAP = 80          # 硬切时的重叠字数


# ---------------------------------------------------------------- 分词

CJK = r"\u4e00-\u9fff"
TOKEN_RE = re.compile(rf"[a-zA-Z][a-zA-Z0-9_\-\.]*|\d+(?:\.\d+)?|[{CJK}]+")

# 功能性虚词与疑问词：对检索零贡献，反而会把 AND 查询拖死
STOP = set("""
的 了 是 和 在 有 会 就 也 都 而 及 与 或 等 从 到 对 为 之 其 这 那 这个 那个
我 你 他 她 它 我们 你们 他们 个 上 下 中 里 后 前 时 说 用 做 能 要 可以 需要
没有 什么 为什么 怎么 怎样 多少 哪里 哪个 如何 是否 吗 呢 啊 吧 其实 应该 还是
一个 一些 这些 那些 现在 然后 因为 所以 但是 如果 已经 还有 就是 不是 有没有
""".split())

# 技术术语：不加进词典会被 jieba 拆碎（rel_z → rel/_/z）
JARGON = """
rel_z rel loc sps tempo rubberband nPVI TTSDS2 Prosogram NISQA DNSMOS DeEAR
dots.tts dots_tts audiocpp mem_saver GGUF Vulkan ONNX cmudict jieba bge
声纹 音色 语速 电平 底噪 音素 韵律 起伏 拆句 吞字 空音 锚点 切片 对齐 相似度
重音 副词 停顿 气口 换气 破音 炸音 削波 峰値 峰值 波峰因数 增益 限幅 归一化
情感 情绪 兴奋 委屈 警惕 紧张 平静 激动 反抗 判据 分位 分位数 阈值 召回率
字幕 台词 旁白 角色 童声 成年 男声 女声 克隆 零样本 微调 推理 显存 并发
""".split()


def _init_jieba():
    import jieba
    jieba.setLogLevel(60)
    for w in JARGON:
        jieba.add_word(w, freq=2000)
    return jieba


_jb = None


def tokenize(text):
    """jieba 搜索引擎模式分词 + 停用词过滤。

    英文标识符必须先用正则整体切出来，否则 jieba 会把
    `stretch_segments` 拆成 `stretch`+`segments`、`rel_z` 拆成 `rel`+`z`。
    早期版本用中文 bigram，会在词边界造大量零语义 token
    （"音节数怎么算" → 数怎/么算），IDF 越高反而越噪声，已废弃。
    """
    global _jb
    if _jb is None:
        _jb = _init_jieba()
    out = []
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9_\.\-]*|\d+(?:\.\d+)?", text):
        out.append(m.group().lower())
    for m in re.finditer(rf"[{CJK}]+", text):
        for t in _jb.cut_for_search(m.group()):
            t = t.strip()
            if t and t not in STOP and len(t) > 1:
                out.append(t)
    return " ".join(out)


# ---------------------------------------------------------------- 切块

HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def chunk_markdown(path, tag):
    """按 markdown 标题切节，节内按段落聚合到 MIN_CHUNK..MAX_CHUNK。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return []

    heads = []           # 当前标题栈 [(level, text)]
    buf = []             # [(lineno, text)]
    buf_len = 0
    chunks = []
    fname = os.path.basename(path)

    def flush():
        nonlocal buf, buf_len
        if not buf:
            return
        text = "\n".join(t for _, t in buf).strip()
        if text:
            hp = " > ".join(h for _, h in heads) if heads else ""
            # 标题路径前置进正文，让 embedding 带上上下文
            body = (f"[{fname}] {hp}\n{text}" if hp else f"[{fname}]\n{text}")
            chunks.append({
                "path": path, "tag": tag,
                "heading": hp,
                "l0": buf[0][0], "l1": buf[-1][0],
                "text": body,
            })
        buf, buf_len = [], 0

    for i, line in enumerate(lines, 1):
        m = HEAD_RE.match(line)
        if m:
            flush()
            lvl = len(m.group(1))
            while heads and heads[-1][0] >= lvl:
                heads.pop()
            heads.append((lvl, m.group(2).strip()))
            buf.append((i, line))
            buf_len += len(line)
            continue
        buf.append((i, line))
        buf_len += len(line) + 1
        if buf_len >= MAX_CHUNK:
            flush()
    flush()

    # 太短的块只在**同一标题内**合并；跨标题合并会把多个主题混成一块，
    # 稀释精确匹配信号（MEMORY.md 这种结论密集文件尤其严重）。
    merged = []
    for c in chunks:
        if merged and len(c["text"]) < MIN_CHUNK:
            prev = merged[-1]
            if (prev["path"] == c["path"] and prev["heading"] == c["heading"]
                    and len(prev["text"]) + len(c["text"]) < MAX_CHUNK * 1.5):
                prev["text"] = prev["text"] + "\n" + c["text"]
                prev["l1"] = c["l1"]
                continue
        merged.append(c)

    # 仍然超长的硬切（带重叠）
    final = []
    for c in merged:
        t = c["text"]
        if len(t) <= MAX_CHUNK * 1.5:
            final.append(c)
            continue
        start = 0
        while start < len(t):
            seg = t[start:start + MAX_CHUNK]
            cc = dict(c)
            cc["text"] = seg
            final.append(cc)
            if start + MAX_CHUNK >= len(t):
                break
            start += MAX_CHUNK - OVERLAP
    return final


def iter_sources():
    conf = DEFAULT_SOURCES
    if os.path.exists(CONF):
        with open(CONF, "r", encoding="utf-8") as f:
            conf = json.load(f).get("sources", DEFAULT_SOURCES)
    import glob as _g
    for s in conf:
        base = s["path"]
        if not os.path.isdir(base):
            continue
        pat = os.path.join(base, s.get("glob", "*.md"))
        for p in sorted(_g.glob(pat, recursive=True)):
            if os.path.isfile(p):
                yield p, s.get("tag", "misc")


# ---------------------------------------------------------------- 向量

_sess = None
_tok = None


def _load_model():
    global _sess, _tok
    if _sess is not None:
        return _sess, _tok
    import onnxruntime as ort
    from tokenizers import Tokenizer
    so = ort.SessionOptions()
    so.intra_op_num_threads = 4
    _sess = ort.InferenceSession(os.path.join(MODEL_DIR, "model.onnx"),
                                 sess_options=so,
                                 providers=["CPUExecutionProvider"])
    _tok = Tokenizer.from_file(os.path.join(MODEL_DIR, "tokenizer.json"))
    _tok.enable_truncation(max_length=512)
    _tok.no_padding()
    return _sess, _tok


def embed(texts, batch=16, prefix=None, progress=False):
    sess, tok = _load_model()
    if prefix:
        texts = [prefix + t for t in texts]
    names = [i.name for i in sess.get_inputs()]
    out = []
    t0 = time.time()
    for i in range(0, len(texts), batch):
        part = texts[i:i + batch]
        encs = tok.encode_batch(part)
        mx = max(len(e.ids) for e in encs)
        ids = np.zeros((len(encs), mx), dtype=np.int64)
        msk = np.zeros((len(encs), mx), dtype=np.int64)
        for j, e in enumerate(encs):
            ids[j, :len(e.ids)] = e.ids
            msk[j, :len(e.ids)] = 1
        feed = {"input_ids": ids, "attention_mask": msk}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.zeros_like(ids)
        h = sess.run(None, feed)[0]
        v = h[:, 0, :]
        v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        out.append(v.astype(np.float32))
        if progress:
            done = min(i + batch, len(texts))
            el = time.time() - t0
            eta = el / done * (len(texts) - done)
            print(f"\r  embed {done}/{len(texts)}  {el:.0f}s  eta {eta:.0f}s",
                  end="", flush=True)
    if progress:
        print()
    return np.vstack(out) if out else np.zeros((0, 512), dtype=np.float32)


# ---------------------------------------------------------------- 建库

def open_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def ensure_schema(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS chunks(
        id INTEGER PRIMARY KEY,
        path TEXT, tag TEXT, heading TEXT,
        l0 INTEGER, l1 INTEGER, text TEXT, sha TEXT, mtime REAL
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(tok, tokenize='unicode61');
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_v USING fts5vocab(fts, row);
    CREATE TABLE IF NOT EXISTS files(
        path TEXT PRIMARY KEY, mtime REAL, size INTEGER, nchunk INTEGER
    );
    """)


def cmd_index(args):
    t_start = time.time()
    c = open_db()
    ensure_schema(c)

    # 旧向量缓存：sha -> vec
    cache = {}
    if os.path.exists(VEC) and os.path.exists(VECIDS):
        old_v = np.load(VEC)
        old_ids = np.load(VECIDS)
        for k, cid in enumerate(old_ids):
            row = c.execute("SELECT sha FROM chunks WHERE id=?", (int(cid),)).fetchone()
            if row and row[0]:
                cache[row[0]] = old_v[k]
    if args.rebuild:
        c.executescript("DELETE FROM chunks; DELETE FROM fts; DELETE FROM files;")
        cache = {}

    seen, added, updated, skipped = set(), 0, 0, 0
    rows = []        # (id, text, sha)

    for path, tag in iter_sources():
        seen.add(path)
        try:
            st = os.stat(path)
        except OSError:
            continue
        prev = c.execute("SELECT mtime,size FROM files WHERE path=?", (path,)).fetchone()
        if prev and abs(prev[0] - st.st_mtime) < 1e-6 and prev[1] == st.st_size and not args.rebuild:
            skipped += 1
            continue

        chunks = chunk_markdown(path, tag)
        if prev:
            old_ids = [r[0] for r in c.execute("SELECT id FROM chunks WHERE path=?", (path,))]
            for cid in old_ids:
                c.execute("DELETE FROM fts WHERE rowid=?", (cid,))
            c.execute("DELETE FROM chunks WHERE path=?", (path,))
            updated += 1
        else:
            added += 1
        for ch in chunks:
            sha = hashlib.sha1(ch["text"].encode("utf-8")).hexdigest()
            cur = c.execute(
                "INSERT INTO chunks(path,tag,heading,l0,l1,text,sha,mtime) VALUES(?,?,?,?,?,?,?,?)",
                (ch["path"], ch["tag"], ch["heading"], ch["l0"], ch["l1"], ch["text"], sha, st.st_mtime))
            cid = cur.lastrowid
            c.execute("INSERT INTO fts(rowid,tok) VALUES(?,?)", (cid, tokenize(ch["text"])))
            rows.append((cid, ch["text"], sha))
        c.execute("INSERT OR REPLACE INTO files(path,mtime,size,nchunk) VALUES(?,?,?,?)",
                  (path, st.st_mtime, st.st_size, len(chunks)))

    # 清掉已删除文件的残留
    for (path,) in c.execute("SELECT path FROM files").fetchall():
        if path not in seen:
            ids = [r[0] for r in c.execute("SELECT id FROM chunks WHERE path=?", (path,))]
            for cid in ids:
                c.execute("DELETE FROM fts WHERE rowid=?", (cid,))
            c.execute("DELETE FROM chunks WHERE path=?", (path,))
            c.execute("DELETE FROM files WHERE path=?", (path,))

    c.commit()

    # 全量重排向量：只为新增/变更的块算 embedding，其余走缓存
    allrows = c.execute("SELECT id,text,sha FROM chunks ORDER BY id").fetchall()
    if not allrows:
        print("没有索引到任何内容")
        return
    need = [r for r in allrows if r[2] not in cache]
    print(f"chunk 总数 {len(allrows)}，文件 新增{added}/更新{updated}/跳过{skipped}，"
          f"需算向量 {len(need)}")
    if need:
        vs = embed([r[1] for r in need], progress=True)
        for k, r in enumerate(need):
            cache[r[2]] = vs[k]
    mat = np.stack([cache[r[2]] for r in allrows]).astype(np.float32)
    ids = np.array([r[0] for r in allrows], dtype=np.int64)
    np.save(VEC, mat)
    np.save(VECIDS, ids)

    sz = os.path.getsize(DB) / 1e6
    print(f"完成：{len(allrows)} 块 / {len(set(r for r in seen))} 文件 / "
          f"库 {sz:.1f}MB / 向量 {mat.nbytes/1e6:.1f}MB / 用时 {time.time()-t_start:.0f}s")


# ---------------------------------------------------------------- 检索

def rrf(rank_lists, k=60, weight=None):
    score = {}
    for ranks in rank_lists:
        for pos, cid in enumerate(ranks):
            w = weight(cid) if weight else 1.0
            score[cid] = score.get(cid, 0.0) + w / (k + pos + 1)
    return sorted(score.items(), key=lambda x: -x[1])


# 蒸馏过的结论文件 > 原始日志。这些文件本身就是"人已经筛过一遍"的结果，
# 同样的词法/语义命中应该排更前，否则长日志靠篇幅把结论挤掉。
AUTH_RULES = [
    ("MEMORY.md", 1.70),
    ("REQUIREMENTS.md", 1.70),
    ("SKILL.md", 1.55),
    ("REPORT_", 1.30),
    ("_STATUS.md", 1.30),
    ("_anchor_report.md", 1.20),
    ("_align_report.md", 1.20),
    ("_proso_report.md", 1.15),
    ("_ttsds_report.md", 1.15),
]


def authority(path):
    base = os.path.basename(path)
    for pat, w in AUTH_RULES:
        if pat in base:
            return w
    return 1.0


def ensure_vocab(c):
    """fts5vocab 用于取每个 token 的文档频率（df），做查询侧的 IDF 过滤。"""
    try:
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts_v USING fts5vocab(fts, row)")
        return True
    except sqlite3.OperationalError:
        return False


def query_tokens(c, q, keep=10):
    """查询 token，保持原文顺序（jieba 已保证 token 干净），并查 df 供渐进砍词用。"""
    raw = [t for t in dict.fromkeys(tokenize(q).split()) if t]
    return raw[:keep]


def _dfs(c, toks):
    df = {}
    try:
        ph = ",".join("?" * len(toks))
        for term, d in c.execute(f"SELECT term, doc FROM fts_v WHERE term IN ({ph})", toks):
            df[term] = d
    except sqlite3.OperationalError:
        pass
    return df


def lex_search(c, q, k=40):
    """多层级 AND 融合。

    只取「第一个成功的 AND」太脆——砍词的顺序一错就全丢。
    改成对每个放宽层级都召回，按保留 token 比例加权合并：
    保留越多 token 的层级越可信。
    """
    toks = query_tokens(c, q)
    if not toks:
        return []
    df = _dfs(c, toks)
    by_freq = sorted(toks, key=lambda t: -df.get(t, 0))   # 高频的先砍
    agg = {}
    L = len(toks)
    for n in range(L, 0, -1):
        drop = set(by_freq[L - n:]) if n < L else set()
        keep = [t for t in toks if t not in drop]
        if not keep:
            continue
        expr = " AND ".join(f'"{t}"' for t in keep)
        try:
            rs = c.execute(
                "SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?",
                (expr, k)).fetchall()
        except sqlite3.OperationalError:
            continue
        w = n / L
        for pos, (rid,) in enumerate(rs):
            agg[rid] = max(agg.get(rid, 0.0), w / (pos + 1))
    return sorted(agg, key=lambda i: -agg[i])[:k]


def vec_search(q, ids, mat, k=40):
    if mat is None or len(ids) == 0:
        return []
    qv = embed([q], prefix=BGE_Q_PREFIX)[0]
    s = mat @ qv
    idx = np.argpartition(-s, min(k, len(s) - 1))[:k]
    idx = idx[np.argsort(-s[idx])]
    return [int(ids[i]) for i in idx]


def load_facts():
    """读账本，并算出 superseded 反查表。

    ★ 2026-11-11 加：账本里同一个坑会留下「当时的结论」和「后来推翻的结论」两条。
    没有 supersedes 字段时检索会把两条一起端上来，读的人无法判断哪条是现行口径
    —— 这正是「RAG 里的固定数据不一定是正确数据」的根因。
    约定：**新条目**写 `"supersedes": ["<旧id>", ...]`，旧条目本身不改（留痕）。
    """
    if not os.path.exists(FACTS):
        return [], {}
    with open(FACTS, "r", encoding="utf-8") as f:
        recs = [json.loads(l) for l in f if l.strip()]
    killed = {}                      # 旧 id -> 取代它的新 id
    for r in recs:
        for old in r.get("supersedes") or []:
            killed[old] = r["id"]
    return recs, killed


def match_facts(q, top=3, min_cov=0.34, latest=True):
    """账本匹配：按查询 token 覆盖率排序，避免长条目靠字数占优。

    latest=True 时剔除被 supersedes 掉的旧条目（默认开 —— 混着旧结论检索比漏检更危险）。
    """
    recs, killed = load_facts()
    qt = set(tokenize(q).split())
    if not qt:
        return []
    scored = []
    for r in recs:
        if latest and r["id"] in killed:
            continue
        hay = set(tokenize(r["topic"] + " " + r["conclusion"] + " "
                           + r.get("evidence", "") + " "
                           + " ".join(r.get("tags", []))).split())
        ov = len(qt & hay)
        if ov and ov / len(qt) >= min_cov:
            scored.append((ov / len(qt), r))
    scored.sort(key=lambda x: -x[0])
    return scored[:top]


def cmd_search(args):
    c = open_db()
    ensure_schema(c)
    n = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    if n == 0:
        print("索引为空，先跑 python rag.py index")
        return
    fh = [] if args.no_facts else match_facts(args.query, top=args.fk,
                                              latest=not getattr(args, "all", False))
    _, killed = load_facts()
    mode = args.mode
    ids, mat = None, None
    if mode in ("hybrid", "vec"):
        if not (os.path.exists(VEC) and os.path.exists(VECIDS)):
            print("向量库缺失，退回词法检索")
            mode = "lex"
        else:
            ids = np.load(VECIDS)
            mat = np.load(VEC)

    lists, names = [], []
    if mode in ("hybrid", "lex"):
        lists.append(lex_search(c, args.query, k=args.k * 5))
        names.append("lex")
    if mode in ("hybrid", "vec"):
        lists.append(vec_search(args.query, ids, mat, k=args.k * 5))
        names.append("vec")

    order = rrf(lists) if len(lists) > 1 else [(i, 0.0) for i in lists[0]]
    if len(lists) > 1:
        # 拿候选块的路径做权威度加权重排
        cand = [cid for cid, _ in order]
        wmap = {}
        for cid in cand:
            r = c.execute("SELECT path FROM chunks WHERE id=?", (cid,)).fetchone()
            if r:
                wmap[cid] = authority(r[0])
        order = rrf(lists, weight=lambda cid: wmap.get(cid, 1.0))
    hits = order[:args.k]
    if not hits:
        print("无结果")
        return

    rank = {cid: pos for pos, (cid, _) in enumerate(hits)}
    out = []
    for cid, sc in hits:
        r = c.execute(
            "SELECT path,tag,heading,l0,l1,text FROM chunks WHERE id=?", (cid,)).fetchone()
        if r:
            out.append({"id": cid, "score": sc, "path": r[0], "tag": r[1],
                        "heading": r[2], "l0": r[3], "l1": r[4], "text": r[5]})

    if args.json:
        print(json.dumps({"facts": [{"cov": round(cv, 2), **r} for cv, r in fh],
                          "chunks": out}, ensure_ascii=False, indent=1))
        return

    print(f"# 检索「{args.query}」mode={mode} 共 {n} 块\n")
    if fh:
        print("== 硬结论账本 ==")
        for cv, r in fh:
            print(f"• [{r['status']}] {r['topic']}  (cov {cv:.2f})")
            print(f"  {r['conclusion']}")
            if r.get("evidence"):
                print(f"  ↳ {r['evidence']}")
            if r["id"] in killed:
                print(f"  ⚠ 已被 {killed[r['id']]} 取代（--all 才应看到这条）")
        print()
    print(f"== 原文片段 top{len(out)} ==")
    for h in out:
        head = h["text"].split("\n")[0]
        body = "\n".join(h["text"].split("\n")[1:]).strip()
        tail = "(空)" if not body else ""
        print(f"—[{h['id']}] {os.path.basename(h['path'])}:{h['l0']}-{h['l1']} "
              f"[{h['tag']}] rrf={h['score']:.4f}")
        if h["heading"]:
            print(f"  § {h['heading']}")
        snip = body[:args.chars].replace("\n", " ⏎ ")
        print(f"  {snip}{tail}{'…' if len(body) > args.chars else ''}\n")


def cmd_get(args):
    c = open_db()
    r = c.execute("SELECT path,tag,heading,l0,l1,text FROM chunks WHERE id=?",
                  (args.id,)).fetchone()
    if not r:
        print("没这个 id")
        return
    print(f"{r[0]}:{r[3]}-{r[4]}  [{r[1]}]  § {r[2]}\n")
    print(r[5])


def cmd_stats(args):
    c = open_db()
    ensure_schema(c)
    n = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    nf = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    print(f"chunk: {n}   文件: {nf}")
    for tag, cnt in c.execute("SELECT tag,COUNT(*) FROM chunks GROUP BY tag ORDER BY 2 DESC"):
        print(f"  {tag:10s} {cnt}")
    if os.path.exists(VEC):
        v = np.load(VEC)
        print(f"向量: {v.shape}  {v.nbytes/1e6:.1f}MB")
    print(f"库: {os.path.getsize(DB)/1e6:.1f}MB" if os.path.exists(DB) else "库: 无")
    nf2 = 0
    if os.path.exists(FACTS):
        with open(FACTS, "r", encoding="utf-8") as f:
            nf2 = sum(1 for _ in f)
    print(f"事实账本: {nf2} 条")


# ---------------------------------------------------------------- 事实账本

def cmd_fact(args):
    q = args.query or args.topic
    if args.action == "add":
        if not args.topic and q:
            args.topic = q
        os.makedirs(os.path.dirname(FACTS), exist_ok=True)
        rec = {
            "id": hashlib.sha1((args.topic + args.conclusion).encode()).hexdigest()[:10],
            "topic": args.topic,
            "conclusion": args.conclusion,
            "evidence": args.evidence or "",
            "status": args.status or "定稿",
            "date": time.strftime("%Y-%m-%d"),
            "tags": [t for t in (args.tags or "").split(",") if t],
        }
        sup = [s.strip() for s in (getattr(args, "supersedes", "") or "").split(",") if s.strip()]
        if sup:
            rec["supersedes"] = sup
        existing, killed = load_facts()
        for e in existing:
            if e["id"] == rec["id"]:
                print(f"已存在同义条 {rec['id']}，未重复写入")
                return
        if sup:
            for old in sup:
                if old not in {e["id"] for e in existing}:
                    print(f"⚠ supersedes 里的 {old} 不在账本里，仍写入但请核对")
        with open(FACTS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"+ {rec['id']}  {rec['topic']}"
              + (f"  (取代 {len(sup)} 条旧结论)" if sup else ""))
        return

    recs, killed = load_facts()
    if not recs:
        print("账本为空")
        return

    if args.action == "list":
        if q:
            recs = [r for r in recs
                    if q.lower() in (r["topic"] + r["conclusion"] + " ".join(r.get("tags", []))).lower()]
        print(f"# 事实账本 {len(recs)} 条\n")
        for r in recs:
            flag = f"  ⚠已被 {killed[r['id']]} 取代" if r["id"] in killed else ""
            print(f"[{r['id']}] {r['date']} ({r['status']}) {r['topic']}{flag}")
            print(f"  {r['conclusion']}")
            if r.get("evidence"):
                print(f"  证据: {r['evidence']}")
            print()
        return

    if args.action == "dup":
        # 主题相近的条目并成一簇：主题 token 做 Jaccard，>=THR 视为同一议题。
        # 账本里没人会给两条结论起一模一样的 topic，靠字符串相等是找不到矛盾的。
        THR = 0.5
        toks = {r["id"]: set(tokenize(r["topic"]).split()) for r in recs}
        parent = {r["id"]: r["id"] for r in recs}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i, a in enumerate(recs):
            ta = toks[a["id"]]
            if not ta:
                continue
            for b in recs[i + 1:]:
                tb = toks[b["id"]]
                if not tb:
                    continue
                j = len(ta & tb) / len(ta | tb)
                if j >= THR:
                    union(a["id"], b["id"])

        clusters = {}
        for r in recs:
            clusters.setdefault(find(r["id"]), []).append(r)
        qn = set(tokenize(q).split()) if q else None
        groups = []
        for v in clusters.values():
            if len(v) < 2:
                continue
            if qn:
                blob = set()
                for r in v:
                    blob |= set(tokenize(r["topic"] + r["conclusion"]).split())
                if not (qn & blob):
                    continue
            groups.append(v)
        groups.sort(key=lambda v: (-len(v), v[0]["topic"]))
        n_open = 0
        print(f"# 同主题多条 {len(groups)} 组（共 {len(recs)} 条）\n")
        for v in groups:
            v = sorted(v, key=lambda r: r.get("date", ""))
            live = [r for r in v if r["id"] not in killed]
            mark = "★ 未归档：多于一条仍在生效" if len(live) > 1 else "已归档"
            n_open += 1 if len(live) > 1 else 0
            print(f"── {v[0]['topic'][:30]}  {len(v)} 条  [{mark}]")
            for r in v:
                f = f" (旧,被 {killed[r['id']]} 取代)" if r["id"] in killed else ""
                print(f"   {r.get('date','')} [{r['id']}]{f} · {r['topic']}")
                print(f"      {r['conclusion'][:110]}")
            print()
        print(f"合计仍并存未归档的组：{n_open}")
        return

    if args.action == "search":
        qt = set(tokenize(q).split())
        scored = []
        for r in recs:
            hay = tokenize(r["topic"] + " " + r["conclusion"] + " " + r.get("evidence", "")
                           + " " + " ".join(r.get("tags", [])))
            ht = set(hay.split())
            ov = len(qt & ht)
            if ov:
                scored.append((ov, r))
        scored.sort(key=lambda x: -x[0])
        print(f"# 账本命中 {min(len(scored), args.k)}/{len(recs)} 条\n")
        for sc, r in scored[:args.k]:
            f = f"  ⚠已被 {killed[r['id']]} 取代" if r["id"] in killed else ""
            print(f"[{r['id']}] ov={sc} {r['topic']}{f}")
            print(f"  {r['conclusion']}")
            if r.get("evidence"):
                print(f"  证据: {r['evidence']}")
            print()


# ---------------------------------------------------------------- main

def cmd_up(args):
    """一条命令完成「记结论 + 增量索引」，这是日常唯一需要记的入口。"""
    if not (args.topic and args.conclusion):
        print("需要 -t 主题 和 -c 结论")
        return
    ns = argparse.Namespace(action="add", topic=args.topic, conclusion=args.conclusion,
                            evidence=args.evidence, status=args.status or "定稿",
                            tags=args.tags, query="",
                            supersedes=getattr(args, "supersedes", ""))
    cmd_fact(ns)
    print("— 刷新索引 —")
    cmd_index(argparse.Namespace(rebuild=False))


def main():
    ap = argparse.ArgumentParser(description="本地 RAG 外部记忆")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index")
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=8)
    p.add_argument("-m", "--mode", default="hybrid", choices=["hybrid", "lex", "vec"])
    p.add_argument("--chars", type=int, default=320)
    p.add_argument("--json", action="store_true")
    p.add_argument("--fk", type=int, default=5, help="账本命中条数")
    p.add_argument("--no-facts", action="store_true")
    p.add_argument("--all", action="store_true",
                   help="连被 supersedes 掉的旧结论一起返回（默认只给现行口径）")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("get")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("stats")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("fact")
    p.add_argument("action", choices=["add", "list", "search", "dup"])
    p.add_argument("query", nargs="?", default="",
                   help="search 的位置参数关键词；add 时等同 -t")
    p.add_argument("-t", "--topic", default="")
    p.add_argument("-c", "--conclusion", default="")
    p.add_argument("-e", "--evidence", default="")
    p.add_argument("-s", "--status", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--supersedes", default="",
                   help="逗号分隔的旧 id，标记本条取代哪些旧结论")
    p.add_argument("-k", type=int, default=6)
    p.set_defaults(func=cmd_fact)

    p = sub.add_parser("up", help="记一条结论并增量刷新索引")
    p.add_argument("-t", "--topic", required=True)
    p.add_argument("-c", "--conclusion", required=True)
    p.add_argument("-e", "--evidence", default="")
    p.add_argument("-s", "--status", default="定稿")
    p.add_argument("--tags", default="")
    p.add_argument("--supersedes", default="",
                   help="逗号分隔的旧 id，标记本条取代哪些旧结论")
    p.set_defaults(func=cmd_up)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
