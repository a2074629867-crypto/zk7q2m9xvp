import os, sys, time, subprocess
from concurrent.futures import ThreadPoolExecutor

URL = "https://dl.fbaipublicfiles.com/speech_expressivity_evaluation/EmphAssess/EmphaClass/EmphaClass-en.tar.gz"
HOST = "dl.fbaipublicfiles.com"
TOT = 3571288236
BASE = "/home/aistudio/models/EmphaClass"
OUT = BASE + "/EmphaClass-en.tar.gz"
CS = 8 * 1024 * 1024
IPS = os.environ.get("IPS", "18.65.214.105").split(",")
W = int(os.environ.get("W", "32"))

def nchunks():
    return (TOT + CS - 1) // CS

def fetch(args):
    i, d = args
    s = i * CS
    e = min(s + CS - 1, TOT - 1)
    want = e - s + 1
    f = os.path.join(d, "c%d" % i)
    try:
        have = os.path.getsize(f)
    except OSError:
        have = 0
    if have >= want:
        return 0
    ip = IPS[i % len(IPS)]
    cmd = ["curl", "-sS", "--max-time", "240", "--resolve", "%s:443:%s" % (HOST, ip),
           "-r", "%d-%d" % (s + have, e), URL]
    with open(f, "ab") as fo:
        subprocess.run(cmd, stdout=fo, stderr=subprocess.DEVNULL)
    return 0

def test():
    d = "/tmp/chunktest"
    os.makedirs(d, exist_ok=True)
    ids = list(range(100, 116))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(fetch, [(i, d) for i in ids]))
    dt = time.time() - t0
    got = sum(os.path.getsize(os.path.join(d, "c%d" % i)) for i in ids)
    print("TEST bytes=%d secs=%.1f speed=%.2fMB/s" % (got, dt, got / dt / 1048576), flush=True)

def main():
    d = BASE + "/chunks"
    os.makedirs(d, exist_ok=True)
    n = nchunks()
    ids = [i for i in range(n) if fetch.__name__ and True]
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=W) as ex:
        futs = [ex.submit(fetch, (i, d)) for i in range(n)]
        last = -1
        while True:
            fin = sum(1 for f in futs if f.done())
            cur = sum(os.path.getsize(os.path.join(d, "c%d" % i)) for i in range(n)
                      if os.path.exists(os.path.join(d, "c%d" % i)))
            if cur != last:
                el = time.time() - t0
                spd = cur / el / 1048576 if el > 0 else 0
                print("CHUNK %d/%d %.1f%% %.2fMB/s eta=%.0fs" %
                      (fin, n, 100.0 * cur / TOT, spd, (TOT - cur) / (spd * 1048576) if spd > 0 else -1), flush=True)
                last = cur
            if fin >= n:
                break
            time.sleep(15)
    cur = sum(os.path.getsize(os.path.join(d, "c%d" % i)) for i in range(n))
    print("CHUNKS_DONE %d / %d" % (cur, TOT), flush=True)
    if cur != TOT:
        print("INCOMPLETE", flush=True)
        return 2
    if os.path.exists(OUT):
        os.remove(OUT)
    with open(OUT, "wb") as fo:
        for i in range(n):
            with open(os.path.join(d, "c%d" % i), "rb") as fi:
                while True:
                    b = fi.read(1 << 22)
                    if not b:
                        break
                    fo.write(b)
    sz = os.path.getsize(OUT)
    print("MERGED size=%d expect=%d match=%s" % (sz, TOT, sz == TOT), flush=True)
    if sz == TOT:
        for i in range(n):
            os.remove(os.path.join(d, "c%d" % i))
        os.rmdir(d)
    return 0 if sz == TOT else 3

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test()
    else:
        sys.exit(main())
