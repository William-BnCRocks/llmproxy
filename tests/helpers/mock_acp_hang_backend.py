import json, sys, time
for line in sys.stdin:
    if not line.strip():
        continue
    req = json.loads(line.strip())
    rid = req.get("id")
    method = req.get("method", "")
    if method == "initialize":
        resp = {"jsonrpc":"2.0","id":rid,"result":{"serverInfo":{},"capabilities":{}}}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    else:
        # simulate hang — never respond
        time.sleep(60)
