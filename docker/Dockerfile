# syntax=docker/dockerfile:1.7
# Isaac Sim 5.1.0, Isaac Lab 2.3.0, Python 3.11 and Torch 2.7/cu128.
FROM nvcr.io/nvidia/isaac-lab:2.3.0@sha256:f1eae1f847cc77e00738d919138d78dde9a12589da9a83b4909555a4abeddb20

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive \
    ACCEPT_EULA=Y PRIVACY_CONSENT=Y OMNI_KIT_ACCEPT_EULA=YES OMNI_KIT_ALLOW_ROOT=1 \
    PHP_DOCKER=1 HSSIM_PYTHON=/opt/php/bin/train-python LOGGER=tensorboard WANDB_MODE=disabled \
    PHP_MOTION_DATABASE_DIR=/data/assets/databases \
    XDG_CACHE_HOME=/data/cache PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=8 \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    PATH=/opt/php/runtimes/train/bin:/opt/php/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git swig curl ca-certificates ffmpeg \
      libgl1 libegl1 libglu1-mesa libosmesa6 libx11-6 libxi6 libxrandr2 \
      libxinerama1 libxcursor1 libxkbcommon0 libvulkan1 tk \
      python3 python3-venv python3-tk \
    && rm -rf /var/lib/apt/lists/*

# netifaces/evdev ship source distributions for Python 3.12.
RUN apt-get update && apt-get install -y --no-install-recommends python3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_CACHE_DIR=/root/.cache/pip

COPY docker/bin/ /opt/php/bin/
COPY docker/constraints*.txt docker/runtime-locks.json /opt/php-build/
COPY thirdparty/holosoma/scripts/constraints/isaacsim-5.1.txt /opt/php-build/isaacsim-5.1.txt
RUN chmod 0755 /opt/php/bin/* \
    && mkdir -p /opt/php/runtimes/{train,motion,inference}/bin /data/assets /data/cache /outputs \
    && for runtime in train motion inference; do \
         ln -s /opt/php/bin/${runtime}-python /opt/php/runtimes/$runtime/bin/python; \
         ln -s /opt/php/bin/${runtime}-python /opt/php/runtimes/$runtime/bin/python3; \
       done

WORKDIR /workspace/php_parkour
COPY thirdparty/holosoma/src/holosoma thirdparty/holosoma/src/holosoma
COPY thirdparty/holosoma/src/holosoma_inference thirdparty/holosoma/src/holosoma_inference
COPY motion_matching motion_matching
COPY pyproject.toml ./

# Retain NVIDIA's Torch/CUDA/Isaac stack. NumPy 1 is needed by Holosoma;
# motion matching and pinocchio require NumPy 2 and use separate venvs.
RUN --mount=type=cache,target=/root/.cache/pip \
    PIP_CONSTRAINT=/opt/php-build/constraints.build.txt train-python -m pip install \
      -c /opt/php-build/isaacsim-5.1.txt -c /opt/php-build/constraints.train.txt \
      -c /opt/php-build/constraints.train-added.txt \
      -e 'thirdparty/holosoma/src/holosoma[unitree,booster]' \
      'mujoco==3.8.1' 'mujoco-python-viewer==0.1.4' 'av==16.1.0' \
      'quadprog==0.1.13' 'PyJWT==2.10.1' \
    && /usr/bin/python3 -m venv /opt/php/envs/motion \
    && /usr/bin/python3 -m venv /opt/php/envs/inference

RUN --mount=type=cache,target=/root/.cache/pip \
    motion-python -m pip install 'pip==26.2.1' \
    && motion-python -m pip install \
      --build-constraint /opt/php-build/constraints.build.txt \
      -c /opt/php-build/constraints.motion.txt -e 'motion_matching[test,registry]' \
    && inference-python -m pip install 'pip==26.2.1' \
    && inference-python -m pip install \
      --build-constraint /opt/php-build/constraints.build.txt \
      -c /opt/php-build/constraints.inference.txt \
      -e 'thirdparty/holosoma/src/holosoma_inference[unitree,booster]' \
      'numpy==2.3.5' 'pytest==9.0.3' 'av==16.1.0'

COPY . .
RUN test ! -e .git && test ! -e thirdparty/holosoma/.git \
    && test ! -e outputs && test ! -e .env.local \
    && PIP_CONSTRAINT=/opt/php-build/constraints.build.txt train-python -m pip install --no-deps -e . \
    && train-python -c 'import torch,numpy,holosoma,wbt_training,mujoco; assert torch.__version__ == "2.7.0+cu128",torch.__version__; assert numpy.__version__ == "1.26.4",numpy.__version__; print("TRAIN_IMPORT_OK",torch.__version__,numpy.__version__,mujoco.__version__)' \
    && motion-python -c 'import motion_matching,numpy,mujoco; print("MOTION_IMPORT_OK",numpy.__version__,mujoco.__version__)' \
    && inference-python -c 'import holosoma_inference,pinocchio,onnxruntime,numpy; print("INFERENCE_IMPORT_OK",numpy.__version__,pinocchio.__version__,onnxruntime.__version__)' \
    && for runtime in train motion inference; do \
         /opt/php/bin/${runtime}-python -m pip freeze > /opt/php-build/${runtime}.freeze.txt; \
       done

ARG PHP_REVISION=unknown
ARG HOLOSOMA_REVISION=unknown
ARG PHP_SOURCE_DIRTY=unknown
LABEL org.opencontainers.image.source="https://github.com/amazon-far/php_parkour" \
      org.opencontainers.image.revision="$PHP_REVISION" \
      org.php-parkour.holosoma-revision="$HOLOSOMA_REVISION" \
      org.php-parkour.source-dirty="$PHP_SOURCE_DIRTY"
ENTRYPOINT ["/opt/php/bin/entrypoint"]
CMD ["sleep", "infinity"]
