import json, sys
for line in sys.stdin:
    if not line.strip():
        continue
    req = json.loads(line.strip())
    rid = req.get("id")
    method = req.get("method", "")
    if method == "initialize":
        resp = {"jsonrpc":"2.0","id":rid,"result":{"serverInfo":{},"capabilities":{}}}
    else:
        resp = {"jsonrpc":"2.0","id":rid,"error":{"code":-32000,"message":"backend exploded"}}
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()
