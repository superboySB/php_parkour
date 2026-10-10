#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$repo"
container=${PHP_CONTAINER:-php-parkour-research}
case "${1:-help}" in
    build) shift; exec bash scripts/research/build_docker.sh "$@" ;;
    up)
        mkdir -p outputs/research/{assets,cache} logs
        exec docker compose -f docker/compose.yml up -d
        ;;
    gui)
        mkdir -p outputs/research/{assets,cache} logs
        exec docker compose -f docker/compose.yml -f docker/compose.gui.yml up -d --force-recreate
        ;;
    down) exec docker compose -f docker/compose.yml down ;;
    exec) shift; exec docker exec "$container" "$@" ;;
    shell) exec docker exec -it "$container" bash ;;
    doctor) shift; exec docker exec "$container" /opt/php/bin/train-python scripts/research/verify_runtime.py "$@" ;;
    train|sim|motion|inference)
        runtime=$1; shift
        [[ $runtime != sim ]] || runtime=train
        exec docker exec "$container" "/opt/php/bin/$runtime-python" "$@"
        ;;
    *) echo 'Usage: docker.sh build|up|gui|down|shell|doctor|exec COMMAND|train ARGS|sim ARGS|motion ARGS|inference ARGS' >&2; exit 2 ;;
esac
