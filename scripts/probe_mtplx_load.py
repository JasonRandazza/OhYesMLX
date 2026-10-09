import json, subprocess, sys, time, urllib.request, os, signal
model, tag = sys.argv[1], sys.argv[2]
extra = sys.argv[3:]
PORT = 8200
log = open(f"probe-{tag}.log", "w")
cmd = [os.path.expanduser("~/.mtplx/bin/mtplx"), "serve", "--model", model, "--host", "127.0.0.1",
       "--port", str(PORT), "--model-id", "probe", "--no-stats-footer", "--ssd-session-cache", "off"] + extra
t0 = time.time()
p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
out = {"cmd": " ".join(cmd)}
try:
    ready = False
    while time.time() - t0 < 300:
        if p.poll() is not None: break
        try:
            h = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)); ready = True; break
        except Exception: time.sleep(2)
    out["exit"] = p.poll(); out["ready"] = ready; out["load_s"] = round(time.time() - t0, 1)
    if ready:
        out["health"] = h
        body = {"model": "probe", "messages": [{"role": "user", "content": "List three prime numbers and say why they are prime."}],
                "max_tokens": 128, "temperature": 0, "stream": True}
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
        chunks = []; text = ""; reasoning = ""
        for raw in urllib.request.urlopen(req, timeout=120):
            line = raw.decode().strip()
            if line.startswith("data:") and line != "data: [DONE]":
                c = json.loads(line[5:]); chunks.append(c)
                for ch in c.get("choices", []):
                    d = ch.get("delta", {}); text += d.get("content") or ""; reasoning += d.get("reasoning_content") or ""
        out["n_chunks"] = len(chunks); out["content"] = text[:300]; out["reasoning"] = reasoning[:300]
        out["last_chunk"] = chunks[-1] if chunks else None
        out["stats_keys"] = [k for c in chunks for k in c if k not in ("choices", "id", "object", "created", "model")][:10]
        out["models"] = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=5))
finally:
    if p.poll() is None:
        os.killpg(p.pid, signal.SIGTERM)
        try: p.wait(20)
        except Exception: os.killpg(p.pid, signal.SIGKILL)
    out["port_free"] = subprocess.run(["lsof", "-ti", f":{PORT}"], capture_output=True).stdout == b""
json.dump(out, open(f"probe-{tag}.json","w"), indent=1)
