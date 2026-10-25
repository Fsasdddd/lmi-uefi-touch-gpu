"""Explicit reviewed checkpoint sequence, in kernel execution order."""
STAGE_CHOICES=(1,5,10,11,12,13,14,15,16,17,18,19,20,50,21,52,53,54,55,56,57,58,59,60,61,62,63)
REVIEWED=(1,2,3,4,5,10,11,30,31,32,33,34,35,12,40,41,42,43,44,13,14,15,16,17,18,19,20,50,21,52,53,54,55,56,57,58,59,60,61,62,63)

def checkpoints_through(stage):
    assert stage in STAGE_CHOICES
    return list(REVIEWED[:REVIEWED.index(stage)+1])
