#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# This benchmark creates a very large graphene flake and uses construct
# to create it.

# This benchmark may be called using:
#
#  python $0
#
# and it may be post-processed using
#
#  python stats.py $0.profile
#
import cProfile
import pstats
import io
import sys
import sisl
import numpy as np

pr = cProfile.Profile()
pr.disable()

randint = np.random.randint

if len(sys.argv) > 1:
    N = int(sys.argv[1])
else:
    N = 200
if len(sys.argv) > 2:
    frac = float(sys.argv[2])
else:
    frac = 0.2
print(f"N = {N}")
print(f"sparsity = {frac}")

# Always fix the random seed to make each profiling concurrent
np.random.seed(1234567890)

pr.enable()
n = int(N * frac)
s = sisl.SparseCSR((N, N), dtype=np.int32)
for i in range(N):
    dat = randint(0, N, n)
    s[i, dat] = 1
pr.disable()
pr.dump_stats(f"{sys.argv[0]}.profile")


stat = pstats.Stats(pr)
# We sort against total-time
stat.sort_stats('tottime')
# Only print the first 20% of the routines.
stat.print_stats('sisl', 0.2)
