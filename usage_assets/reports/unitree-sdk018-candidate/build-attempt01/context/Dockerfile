# Independent CPU-built candidate; never replaces the research base tag.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
LABEL org.php-research.sdk-candidate="far-unitree-sdk-0.1.8-import-only" \
      org.php-research.base-config-id="sha256:88254ac0b90a3056375145601d741aa3e08726e18412d201a3c7e7915a23996f"
COPY wheels/ /opt/php-sdk018/wheels/
COPY wheel-manifest.json abi_probe.py baseline-train.json baseline-inference.json baseline-motion.json /opt/php-sdk018/
RUN --network=none /usr/bin/python3 -c 'import hashlib,json,pathlib; p=pathlib.Path("/opt/php-sdk018"); m=json.loads((p/"wheel-manifest.json").read_text()); assert len(m["wheels"])==2; [(lambda b,w: (b.stat().st_size==w["bytes"] and hashlib.sha256(b.read_bytes()).hexdigest()==w["sha256"]) or (_ for _ in ()).throw(AssertionError(w["filename"])))(p/"wheels"/w["filename"],w) for w in m["wheels"]]'
# train-python is Isaac Kit Python 3.11, not a venv. Only this new layer is changed.
RUN --network=none PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    /opt/php/bin/train-python -m pip install --no-index --no-deps --force-reinstall \
      /opt/php-sdk018/wheels/far_unitree_sdk-0.1.8-cp311-cp311-manylinux_2_31_x86_64.whl \
    && PIP_CONFIG_FILE=/dev/null PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    /opt/php/bin/inference-python -m pip install --no-index --no-deps --force-reinstall \
      /opt/php-sdk018/wheels/far_unitree_sdk-0.1.8-cp312-cp312-manylinux_2_31_x86_64.whl
# No native SDK constructors, DDS, CUDA, SimulationApp or simulator is called.
RUN --network=none CUDA_VISIBLE_DEVICES= NVIDIA_VISIBLE_DEVICES=none \
    /opt/php/bin/train-python /opt/php-sdk018/abi_probe.py --runtime train \
      --baseline /opt/php-sdk018/baseline-train.json --output /opt/php-sdk018/build-train.json \
    && CUDA_VISIBLE_DEVICES= NVIDIA_VISIBLE_DEVICES=none \
    /opt/php/bin/inference-python /opt/php-sdk018/abi_probe.py --runtime inference \
      --baseline /opt/php-sdk018/baseline-inference.json --output /opt/php-sdk018/build-inference.json \
    && CUDA_VISIBLE_DEVICES= NVIDIA_VISIBLE_DEVICES=none \
    /opt/php/bin/motion-python /opt/php-sdk018/abi_probe.py --runtime motion \
      --baseline /opt/php-sdk018/baseline-motion.json --output /opt/php-sdk018/build-motion.json \
    && /opt/php/bin/train-python -m pip freeze > /opt/php-sdk018/train.freeze.txt \
    && /opt/php/bin/inference-python -m pip freeze > /opt/php-sdk018/inference.freeze.txt \
    && /opt/php/bin/motion-python -m pip freeze > /opt/php-sdk018/motion.freeze.txt
