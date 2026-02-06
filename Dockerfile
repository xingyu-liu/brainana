ARG DEBIAN_FRONTEND=noninteractive

##############
# ANTs build #
##############
FROM debian:bookworm-slim AS ants-builder

ARG DEBIAN_FRONTEND
ARG ANTS_VERSION=v2.5.0

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      cmake \
      git \
      ninja-build \
      wget && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${ANTS_VERSION}" https://github.com/ANTsX/ANTs.git /usr/local/src/ants
WORKDIR /tmp/ants-build
RUN mkdir -p /opt/ants && \
    cmake -GNinja \
      -DBUILD_TESTING=OFF \
      -DRUN_LONG_TESTS=OFF \
      -DRUN_SHORT_TESTS=OFF \
      -DBUILD_SHARED_LIBS=ON \
      -DCMAKE_INSTALL_PREFIX=/opt/ants \
      /usr/local/src/ants && \
    cmake --build . --parallel && \
    cd ANTS-build && \
    cmake --install . && \
    test -x /opt/ants/bin/antsRegistration || (echo "ERROR: antsRegistration not found after install" && exit 1)

###########################
# Python env builder      #
# (build-essential only  #
#  here, not in final)   #
###########################
FROM debian:bookworm-slim AS python-builder

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      libsuitesparse-dev \
      python3 \
      python3-dev \
      python3-venv && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/

WORKDIR /opt/brainana
COPY pyproject.toml uv.lock setup.cfg ./
COPY . .

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN mkdir -p /opt/brainana/tmp && \
    uv venv /opt/venv && \
    TMPDIR=/opt/brainana/tmp uv sync --python /opt/venv/bin/python --frozen --no-cache || \
    TMPDIR=/opt/brainana/tmp uv pip install --no-cache -e . && \
    rm -rf /opt/brainana/tmp

#########################
# Runtime with all libs #
#########################
FROM debian:bookworm-slim

ARG DEBIAN_FRONTEND
ARG FSL_VERSION=6.0.5.1
ARG FREESURFER_VERSION=7.4.1
ARG FREESURFER_TARBALL=freesurfer-linux-ubuntu22_amd64-${FREESURFER_VERSION}.tar.gz
ARG AFNI_TARBALL=linux_rocky_8.tgz

# Install uv (pinned version for reproducibility)
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    TERM=xterm-256color

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      bc \
      bzip2 \
      ca-certificates \
      curl \
      dc \
      git \
      gosu \
      locales \
      netpbm \
      perl \
      python3 \
      python3-pip \
      python3-venv \
      tar \
      tcsh \
      wget \
      openjdk-17-jre-headless \
      # procps provides 'ps', required by Nextflow to collect task metrics \
      procps \
      # CHOLMOD runtime for scikit-sparse (no build-essential in final image) \
      libcholmod3 \
      # graphics/openGL + X11 runtime for AFNI/FSL/FreeSurfer \
      freeglut3-dev \
      libfontconfig1 \
      libfreetype6 \
      libgl1 \
      libglw1-mesa \
      libglu1-mesa \
      libgomp1 \
      libgsl27 \
      libgslcblas0 \
      libice6 \
      libjpeg62-turbo \
      libmotif-common \
      libopenblas0 \
      libpng16-16 \
      libquadmath0 \
      libsm6 \
      libx11-6 \
      libxau6 \
      libxcb1 \
      libxcomposite1 \
      libxcursor1 \
      libxdamage1 \
      libxdmcp6 \
      libxext6 \
      libxfixes3 \
      libxi6 \
      libxinerama1 \
      libxmu6 \
      libxm4 \
      libxpm4 \
      libxrandr2 \
      libxrender1 \
      libxshmfence1 \
      libxt6 \
      libxxf86vm1 \
      zlib1g \
      # Connectome Workbench for QC surface snapshots (wb_command) and xvfb for headless rendering \
      connectome-workbench \
      xauth \
      xvfb && \
    sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen && \
    rm -rf /var/lib/apt/lists/*

######################
# Install ANTs build #
######################
COPY --from=ants-builder /opt/ants /opt/ants

# Add neuro user to handle permissions
ARG USER_ID=1000
ARG GROUP_ID=1000

RUN groupadd -g ${GROUP_ID} neuro && \
    useradd -l -u ${USER_ID} -g neuro -m neuro && \
    usermod -aG sudo neuro || true

###########
# Install FSL
###########
ENV FSLDIR=/usr/local/fsl
RUN curl -fsSL "https://fsl.fmrib.ox.ac.uk/fsldownloads/fsl-${FSL_VERSION}-centos7_64.tar.gz" \
    | tar xz -C /usr/local
ENV FSLOUTPUTTYPE=NIFTI_GZ \
    FSLMULTIFILEQUIT=TRUE

############
# Install AFNI
############
ENV AFNI_HOME=/usr/local/afni
RUN mkdir -p "${AFNI_HOME}" && \
    curl -fsSL "https://afni.nimh.nih.gov/pub/dist/tgz/${AFNI_TARBALL}" \
      | tar xz -C "${AFNI_HOME}" --strip-components=1

################
# Install FreeSurfer
# Ubuntu 22 build is the best match for Debian bookworm (similar glibc 2.35/2.36).
# See https://surfer.nmr.mgh.harvard.edu/fswiki/rel7downloads
################
ENV FREESURFER_HOME=/usr/local/freesurfer
RUN curl -fsSL "https://surfer.nmr.mgh.harvard.edu/pub/dist/freesurfer/${FREESURFER_VERSION}/${FREESURFER_TARBALL}" -o /tmp/freesurfer.tar.gz && \
    tar --no-same-owner -xzvf /tmp/freesurfer.tar.gz -C /usr/local && \
    rm /tmp/freesurfer.tar.gz && \
    rm -rf "${FREESURFER_HOME}/docs" "${FREESURFER_HOME}/matlab" "${FREESURFER_HOME}/average" "${FREESURFER_HOME}/trctrain" 2>/dev/null || true

##############
# Environment
##############
ENV ANTSPATH=/opt/ants/bin/ \
    FSLDIR=/usr/local/fsl \
    AFNI_HOME=/usr/local/afni \
    AFNIPATH=/usr/local/afni \
    FREESURFER_HOME=/usr/local/freesurfer \
    FS_LICENSE=/fs_license.txt \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

ENV PATH=${FSLDIR}/bin:${AFNI_HOME}:${ANTSPATH}:${FREESURFER_HOME}/bin:${JAVA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=/opt/ants/lib:${FSLDIR}/lib
ENV SUBJECTS_DIR=${FREESURFER_HOME}/subjects \
    LOCAL_DIR=${FREESURFER_HOME}/local \
    FS_OVERRIDE=0 \
    FIX_VERTEX_AREA="" \
    FSF_OUTPUT_FORMAT=nii.gz \
    OS=Linux \
    FREESURFER=${FREESURFER_HOME} \
    FSFAST_HOME=${FREESURFER_HOME}/fsfast \
    FMRI_ANALYSIS_DIR=${FREESURFER_HOME}/fsfast \
    FUNCTIONALS_DIR=${FREESURFER_HOME}/sessions \
    MINC_BIN_DIR=${FREESURFER_HOME}/mni/bin \
    MINC_LIB_DIR=${FREESURFER_HOME}/mni/lib \
    MNI_DIR=${FREESURFER_HOME}/mni \
    MNI_DATAPATH=${FREESURFER_HOME}/mni/data \
    MNI_PERL5LIB=${FREESURFER_HOME}/mni/share/perl5 \
    PERL5LIB=${FREESURFER_HOME}/mni/share/perl5 \
    PYTHONPATH=/opt/brainana/src

# Create a shell script to source environments
RUN printf '#!/bin/bash\n\
# Neuroimaging tools environment\n\
export FSLDIR=%s\n\
export AFNI_HOME=%s\n\
export AFNIPATH=%s\n\
export ANTSPATH=%s\n\
export FREESURFER_HOME=%s\n\
export FS_LICENSE=%s\n\
export FSLOUTPUTTYPE=NIFTI_GZ\n\
export PATH=$FSLDIR/bin:$AFNI_HOME:$ANTSPATH:$FREESURFER_HOME/bin:${JAVA_HOME}/bin:/usr/local/bin:$PATH\n\
\n\
# License check\n\
if [ ! -f "$FS_LICENSE" ]; then\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "WARNING: FreeSurfer license not found at $FS_LICENSE"\n\
    echo "To run FreeSurfer tools, please mount your license file:"\n\
    echo "  docker run ... -v /path/to/license.txt:/fs_license.txt ..."\n\
    echo "--------------------------------------------------------------------------------"\n\
fi\n\
\n\
# Welcome Message\n\
if [ "$PS1" ]; then\n\
    echo "================================================================================"\n\
    echo "Welcome to brainana Interactive Environment"\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "Installed Tools:"\n\
    echo "  - FSL:        \$(fslval 2>/dev/null | head -n 1 || echo \"Installed\")"\n\
    echo "  - ANTs:       \$(antsRegistration --version | grep Version | head -n 1 || echo \"Installed\")"\n\
    echo "  - AFNI:       \$(afni -version | head -n 1 || echo \"Installed\")"\n\
    echo "  - FreeSurfer: \$(cat \$FREESURFER_HOME/build-stamp.txt 2>/dev/null || echo \"Installed\")"\n\
    echo "  - Python:     \$(python3 --version)"\n\
    echo "  - Java:       \$(java -version 2>&1 | head -n 1)"\n\
    echo "  - uv:         \$(uv --version)"\n\
    echo "  - Nextflow:   \$(nextflow -version 2>/dev/null | head -n 1 || echo \"Installed\")"\n\
    echo "  - Workbench:  \$(wb_command -version 2>/dev/null | head -n 1 || echo \"Installed\")"\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "Usage Examples:"\n\
    echo "  ./run_brainana.sh run main.nf --bids_dir /data --output_dir /output"\n\
    echo "  python3 -m nhp_mri_prep.config.config_generator_cli"\n\
    echo "================================================================================"\n\
fi\n' \
    "${FSLDIR}" "${AFNI_HOME}" "${AFNIPATH}" "${ANTSPATH}" "${FREESURFER_HOME}" "${FS_LICENSE}" \
    > /etc/profile.d/neuroenv.sh && \
    chmod +x /etc/profile.d/neuroenv.sh

# Setup Bash for interactive use
RUN echo "source /etc/profile.d/neuroenv.sh" >> /etc/bash.bashrc && \
    echo "alias ls='ls --color=auto'" >> /etc/bash.bashrc && \
    echo "alias ll='ls -alF'" >> /etc/bash.bashrc

##############
# Nextflow
##############
ARG NEXTFLOW_VERSION=25.10.2
# Pin version at runtime to prevent auto-update and version drift
ENV NXF_VER=${NEXTFLOW_VERSION}
# Pre-cache framework JAR so no network is needed at runtime
ENV NXF_HOME=/opt/nextflow

WORKDIR /tmp
RUN curl -s https://get.nextflow.io | bash && \
    chmod +x nextflow && \
    mv nextflow /usr/local/bin/ && \
    nextflow -version && \
    chmod -R a+rX /opt/nextflow

#################
# Project Install (from builder – no gcc/build-essential in final image)
#################
WORKDIR /opt/brainana

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Redirect caches to writable locations to support arbitrary UIDs
ENV MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONPYCACHEPREFIX=/tmp/pycache

COPY --from=python-builder /opt/venv /opt/venv
COPY --from=python-builder /opt/brainana /opt/brainana

# World-writable temp dirs so any UID (via -u or gosu) can use them
# .nextflow/ in project dir must be writable (Nextflow writes session metadata there)
RUN mkdir -p /tmp/matplotlib /tmp/pycache /tmp/.X11-unix /tmp/home && \
    chmod 1777 /tmp/matplotlib /tmp/pycache /tmp/.X11-unix /tmp/home && \
    chmod -R 755 /opt/brainana /opt/venv /home/neuro && \
    chmod +x /opt/brainana/entrypoint.sh && \
    mkdir -p /opt/brainana/.nextflow && \
    chmod 1777 /opt/brainana/.nextflow

# Pre-generate matplotlib font cache at build time so any UID can read it.
# Without this, the HEALTHCHECK (root) or first runtime import creates it as
# root-owned, and non-root pipeline users get "Permission denied".
RUN python3 -c "import matplotlib.font_manager" 2>/dev/null || true && \
    chmod -R a+rw /tmp/matplotlib 2>/dev/null || true

# NOTE: No "USER neuro" here. The entrypoint starts as root,
# detects the UID of /output, and drops to that user via gosu.
WORKDIR /opt/brainana

# Health check: lightweight probe that doesn't import matplotlib (which would
# create a root-owned font cache that blocks non-root pipeline users).
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "print('OK')" || exit 1

# Labels for image metadata
LABEL org.opencontainers.image.title="brainana" \
      org.opencontainers.image.description="Macaque MRI preprocessing pipeline" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/yourusername/brainana"

ENTRYPOINT ["/opt/brainana/entrypoint.sh"]
CMD ["/input", "/output"]
