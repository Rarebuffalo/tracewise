import re,sys,os,glob
Q={
'wr_section':(r'webhook-events-and-payloads',r'## workflow_run'),
}
pats=[
 ('PAYLOAD_CAP',r'capped at 25 MB'),
 ('NO_AUTO_REDELIVER',r'not automatically redeliver'),
 ('DELIVERY_ID_SAME',r'X-GitHub-Delivery.{0,120}(same|unique)'),
 ('TEN_SECONDS',r'within 10 seconds'),
 ('ORDER',r'(?i)(out of order|in the order|order in which|guarantee.{0,40}order)'),
 ('SIG',r'(?i)(constant[- ]time|timing attack|X-Hub-Signature-256)'),
 ('STARTUP_FAILURE',r'startup_failure'),
 ('WR_COMPLETED',r'(?i)regardless of whether the workflow'),
 ('RERUN_SHA',r'(?i)re-?run.{0,120}(same|GITHUB_SHA|commit)'),
 ('FORK_SECRETS',r'(?i)secrets are not passed'),
 ('FORK_PRS_EMPTY',r'(?i)forked repository.{0,80}empty .?pull_requests'),
 ('LOG_EXPIRY',r'expires after 1 minute'),
 ('COMPARE_LIMITS',r'(?i)(250 commits|300 (changed )?files)'),
 ('CONTENTS_LIMITS',r'(?i)(1 MB|100 MB|symlink|submodule)'),
 ('LIMIT_6553',r'6553[56]'),
 ('ANNOT_50',r'(?i)maximum of 50'),
 ('TOKEN_HOUR',r'expire after 1 hour'),
 ('RL_INSTALL',r'(?i)(5,000 requests per hour|12,500|15,000 requests)'),
 ('RL_SECONDARY',r'(?i)(100 concurrent|900 points|80 content|500 content)'),
 ('RETENTION',r'(?i)retained for 90 days|between 1 day or (90|400) days'),
 ('PERM_CHANGE',r'(?i)(new_permissions_accepted|accept the new permissions|approve the (new|updated) permissions)'),
 ('INSTALL_DELETED',r'(?i)(installation.{0,30}deleted|uninstall)'),
 ('APP_DELIVERIES',r'(GET|POST) /app/hook/deliveries[^\s|`]*'),
 ('CHECK_SUITE_PR',r'(?i)only (look|detect).{0,80}push'),
]
for f in sorted(glob.glob('docs/*.md')):
    lines=open(f,encoding='utf-8',errors='replace').read().split('\n')
    for i,l in enumerate(lines,1):
        for name,p in pats:
            if re.search(p,l):
                print(f"{name}\t{os.path.basename(f)}:{i}\t{l.strip()[:260]}")
