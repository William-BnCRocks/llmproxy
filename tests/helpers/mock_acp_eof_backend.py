import json, sys
line = sys.stdin.readline()
req = json.loads(line.strip())
resp = {"jsonrpc":"2.0","id":req["id"],"result":{"serverInfo":{},"capabilities":{}}}
sys.stdout.write(json.dumps(resp) + "\n")
sys.stdout.flush()
# exit immediately — next read will hit EOF
sys.exit(0)
