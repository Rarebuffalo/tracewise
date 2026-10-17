import json, re, sys, glob, os
RED = re.compile(r'(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?i:authorization:\s*(?:bearer|token)\s+)\S+)')
def red(s): return RED.sub('[REDACTED]', s)
files = sys.argv[1:]
for f in files:
    tag = os.path.basename(f)[:22]
    uses = {}
    for line in open(f, errors='replace'):
        try: o = json.loads(line)
        except: continue
        ts = o.get('timestamp','')
        msg = o.get('message') or {}
        content = msg.get('content') if isinstance(msg, dict) else None
        if not isinstance(content, list): continue
        for c in content:
            if c.get('type') == 'tool_use' and c.get('name') == 'Bash':
                cmd = c['input'].get('command','')
                if re.search(r'\bgh\b|api\.github\.com|Authorization|GITHUB_TOKEN|GH_TOKEN|auth (status|token|login|logout)', cmd):
                    uses[c['id']] = (ts, cmd)
                    print(f"=== [{tag}] {ts} CMD:\n{red(cmd)[:1500]}")
            elif c.get('type') == 'tool_result' and c.get('tool_use_id') in uses:
                out = c.get('content')
                if isinstance(out, list): out = ' '.join(x.get('text','') for x in out if isinstance(x, dict))
                out = str(out)
                if re.search(r'Logged in|account|auth', out, re.I):
                    print(f"--- RESULT (auth-related lines):")
                    for l in out.splitlines():
                        if re.search(r'Logged in|account|Token scopes|Active|auth', l, re.I): print('   ', red(l)[:300])
