"""Load-test every newly registered Gate2 package runner before server restart."""
import sys
APP = r"C:\Users\Leandro\Desktop\Leandro\AI 222 and AI 231\Exercise 2\Exercise 2b\vcm_live_test_local\vcm_live_test_local"
if APP not in sys.path:
    sys.path.insert(0, APP)
import gate1_server as gs

NAMES = [
    "gate2v58_smooth_pidgate",
    "gate2v59_focal_warp",
    "gate2v60_phone_warp",
    "gate2v61_keyword_mix",
    "gate2v62_speechtrim",
    "gate2v63_pca_frontend",
    "gate2v64_paired_negatives",
    "gate2v64c_stochmel",
    "gate2v64d_expandedneg",
    "gate2v64p_paired_owner",
    "gate2v65_stoch15k",
]
fail = 0
for n in NAMES:
    try:
        r = gs.Gate2PackageRunner(n)
        print("OK   {0} frames={1} mels={2} ch={3} labels={4}".format(n, r.frames, r.n_mels, r.channels, len(r.labels)))
    except Exception as exc:
        fail += 1
        print("FAIL {0}: {1}".format(n, exc))
print("RESULT fail=" + str(fail))
sys.exit(1 if fail else 0)
