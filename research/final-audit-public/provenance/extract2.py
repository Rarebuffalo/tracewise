import json, re, sys, os, glob
RED = re.compile(r'(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?i:authorization:\s*(?:bearer|token)\s+)\S+)')
red=lambda s: RED.sub('[REDACTED]', s)
mode=sys.argv[1]; files=sys.argv[2:]
repos=set(); evid={}
for f in files:
    uses={}
    for line in open(f, errors='replace'):
        try: o=json.loads(line)
        except: continue
        m=o.get('message') or {}
        cs=m.get('content') if isinstance(m,dict) else None
        if not isinstance(cs,list): continue
        for c in cs:
            if c.get('type')=='tool_use' and c.get('name')=='Bash':
                cmd=c['input'].get('command',''); uses[c['id']]=(o.get('timestamp',''),cmd,os.path.basename(f)[:20])
                if re.search(r'\bgh\b',cmd):
                    for mm in re.finditer(r'repos/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)',cmd): repos.add(mm.group(1))
                    for mm in re.finditer(r'"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+) \d+"',cmd): repos.add(mm.group(1))
                    for mm in re.finditer(r'for r in ([^;]+?); do',cmd):
                        for t in mm.group(1).split():
                            if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',t): repos.add(t)
                for mm in re.finditer(r'(?:>|tee|cp \S+)\s*(\S*final-audit/evidence/\S+|[\w./-]+\.(?:json|md|txt|log|zip|err|html|py|toml|yml))',cmd):
                    evid.setdefault(mm.group(1),[]).append((o.get('timestamp',''),'gh' if re.search(r'\bgh\b',cmd) else ('curl' if 'curl' in cmd else 'other')))
            elif c.get('type')=='tool_result' and c.get('tool_use_id') in uses and mode=='search':
                ts,cmd,tag=uses[c['tool_use_id']]
                if 'search/' in cmd and re.search(r'\bgh\b',cmd):
                    out=c.get('content'); out=' '.join(x.get('text','') for x in out if isinstance(x,dict)) if isinstance(out,list) else str(out)
                    print('=== ',tag,ts,'\n',red(cmd)[:600],'\n--- OUT:\n',red(out)[:3000])
if mode=='repos': print('\n'.join(sorted(repos)))
if mode=='evid':
    for k,v in sorted(evid.items()): print(k, sorted(set(x[1] for x in v)), v[0][0])
