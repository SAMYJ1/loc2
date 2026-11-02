#!/usr/bin/env python3
"""Bounded acceptance observation, never applies a location or follows a new session."""
import argparse,json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from loc2.cli import request_stop
p=argparse.ArgumentParser();p.add_argument('--minutes',type=int,default=120);p.add_argument('--output',required=True,type=Path);args=p.parse_args()
assert 1<=args.minutes<=180
state=Path.home()/'.config/loc2/latest-status.private.json'
args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
print('WAITING_FOR_USER_APPLIED_SESSION',flush=True)
wait_end=time.monotonic()+600;identity=None
while time.monotonic()<wait_end:
    snapshot=json.loads(state.read_text())
    if snapshot.get('sessionActive') and snapshot.get('helperAcceptedBatches',0)>0:
        identity=(snapshot.get('controlEpoch'),snapshot.get('sessionId'));revision=snapshot['controlRevision'];break
    time.sleep(1)
if identity is None:raise SystemExit('No reporting session was started')
started=time.monotonic();first=snapshot;last=snapshot;reason='duration-complete';count=0;subscriptions=0
print('ACCEPTANCE_STARTED',flush=True)
with (args.output/'observations.jsonl').open('w') as log:
    while time.monotonic()-started<args.minutes*60:
        now=time.monotonic();snapshot=json.loads(state.read_text())
        if (snapshot.get('controlEpoch'),snapshot.get('sessionId'))!=identity or not snapshot.get('sessionActive'):
            reason='session-ended-before-duration';break
        if snapshot['controlRevision']!=revision:reason='target-or-session-changed';break
        if time.time()-snapshot['updatedAt']>5:reason='service-observation-stale';break
        record={key:snapshot.get(key) for key in ['state','connected','subscribed','videoReady','helperAcceptedBatches','queuedMessages','videoReceivedFrames','videoDecodedFrames','diagnosticStage','error']}
        record['elapsedSeconds']=round(now-started,1);log.write(json.dumps(record,ensure_ascii=False)+'\n');log.flush()
        last=snapshot;count+=1;subscriptions+=int(bool(snapshot['subscribed']))
        time.sleep(5)
    if reason=='duration-complete':
        current=json.loads(state.read_text())
        if (current.get('controlEpoch'),current.get('sessionId'))==identity and current['controlRevision']==revision and time.time()-current['updatedAt']<5:
            request_stop(current)
        else:reason='session-changed-at-deadline'
    elif reason=='service-observation-stale':
        # Stop only the original run, never a later replacement session.
        try:request_stop(first)
        except (FileNotFoundError,FileExistsError):pass
result=dict(reason=reason,elapsedSeconds=round(time.monotonic()-started,1),samples=count,subscribedSamples=subscriptions,
            firstBatches=first['helperAcceptedBatches'],lastBatches=last['helperAcceptedBatches'],
            lastQueuedMessages=last['queuedMessages'],lastDecodedFrames=last.get('videoDecodedFrames'),
            adoption='requires-native-app-observation',recovery='requires-native-app-observation')
(args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result),flush=True)
