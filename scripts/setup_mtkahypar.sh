#!/usr/bin/env bash
# Build UNPATCHED upstream Mt-KaHyPar (pinned) with the Python module.
# FastPart v0 needs only the engine's stock Python API: no source patches.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
PIN=6271a58cfc6492cb97a34502fa9040cab0e64092
mkdir -p "$here/external"
if [ ! -d "$here/external/mt-kahypar" ]; then
  git clone https://github.com/kahypar/mt-kahypar.git "$here/external/mt-kahypar"
fi
cd "$here/external/mt-kahypar"
git fetch -q origin "$PIN" 2>/dev/null || true
git checkout -q "$PIN"
git submodule update --init --recursive
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DKAHYPAR_PYTHON=ON -DKAHYPAR_DOWNLOAD_TBB=ON -DKAHYPAR_DISABLE_HWLOC=ON
cmake --build build --parallel "$(nproc)"
echo "python module: $here/external/mt-kahypar/build/python"
