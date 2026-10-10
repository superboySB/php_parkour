#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$repo"
test -f thirdparty/holosoma/src/holosoma/pyproject.toml || {
    echo 'Initialize the pinned Holosoma first: git submodule update --init --recursive' >&2
    exit 2
}
mkdir -p outputs/research/docker
build_log="outputs/research/docker/build-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
# Keep each attempt's file descriptor independent, including during cancellation.
ln -sfn "$(basename -- "$build_log")" outputs/research/docker/build.log
source_dirty=false
[[ -z "$(git status --porcelain)" ]] || source_dirty=true
docker build --progress=plain \
    --build-arg "PHP_REVISION=$(git rev-parse HEAD)" \
    --build-arg "HOLOSOMA_REVISION=$(git -C thirdparty/holosoma rev-parse HEAD)" \
    --build-arg "PHP_SOURCE_DIRTY=$source_dirty" \
    -f docker/Dockerfile -t "${PHP_IMAGE:-php-parkour:research}" . \
    2>&1 | tee "$build_log"
docker image inspect "${PHP_IMAGE:-php-parkour:research}" \
    --format '{{json .}}' > outputs/research/docker/image-inspect.json
