"""Bank canned action-scenario takes from synthetic_samples via the lab save API (idempotent)."""
import base64, glob, io, json, urllib.request, wave
from pathlib import Path
import numpy as np

SS = Path('synthetic_samples')
SR = 16000
BASE = 'http://127.0.0.1:8765'

def load(pat):
    hits = sorted(glob.glob(str(SS / pat)))
    assert hits, 'missing sample: ' + pat
    with wave.open(hits[0], 'rb') as h:
        sr, ch, sw = h.getframerate(), h.getnchannels(), h.getsampwidth()
        assert (sr, ch, sw) == (SR, 1, 2), (hits[0], sr, ch, sw)
        return np.frombuffer(h.readframes(h.getnframes()), dtype=np.int16)

def sil(s):
    return np.zeros(int(SR * s), dtype=np.int16)

def tone(s, f0, f1, amp=0.12):
    t = np.arange(int(SR * s)) / SR
    f = np.linspace(f0, f1, t.size)
    return (amp * np.sin(2 * np.pi * f * t) * 32767).astype(np.int16)

def wav64(audio):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as h:
        h.setnchannels(1); h.setsampwidth(2); h.setframerate(SR)
        h.writeframes(audio.astype(np.int16).tobytes())
    return base64.b64encode(buf.getvalue()).decode()

def http_json(path, data=None, method='GET'):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json'}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

existing = {str(x.get('label', '')): x['id'] for x in http_json('/api/recordings').get('recordings', [])}

wake_n = load('gate1_wake_nova_*.wav')
wake_p = load('gate1_wake_piattos_*.wav')
s_play = load('gate2_PLAY_MUSIC_*.wav')
s_stop = load('gate2_STOP_*.wav')
s_pause = load('gate2_PAUSE_*.wav')
s_light = load('gate2_LIGHT_ON_*.wav')

scenarios = [
    ('scenario S1: Nova -> Play music', [sil(0.6), wake_n, sil(0.35), s_play, sil(1.2)]),
    ('scenario S2: Nova -> Stop', [sil(0.6), wake_n, sil(0.35), s_stop, sil(1.2)]),
    ('scenario S3: Nova -> Stop x2 (repeat)', [sil(0.6), wake_n, sil(0.35), s_stop, sil(0.5), s_stop, sil(1.2)]),
    ('scenario S4: Piattos -> Light on', [sil(0.6), wake_p, sil(0.35), s_light, sil(1.2)]),
    ('scenario S5: Nova -> Pause', [sil(0.6), wake_n, sil(0.35), s_pause, sil(1.2)]),
    ('scenario S6: tone only (negative)', [sil(0.8), tone(5.0, 440, 880), sil(1.2)]),
]

for label, parts in scenarios:
    if label in existing:
        print('SKIP (already banked):', label)
        continue
    d = http_json('/api/recordings', {'wav_base64': wav64(np.concatenate(parts)), 'label': label}, 'POST')
    e = d.get('recording', d)
    print('UPLOADED:', label, '->', e.get('id'), round(e.get('duration_s', 0), 2), 's')

scn = [x for x in http_json('/api/recordings').get('recordings', []) if str(x.get('label', '')).startswith('scenario ')]
print('SCENARIOS BANKED:', len(scn))
for x in scn:
    print('  ', x['id'], '|', x['label'], '|', x.get('duration_s'), 's')
