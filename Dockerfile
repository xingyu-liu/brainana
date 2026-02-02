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
    cmake --install . && \
    test -d /opt/ants && ls -la /opt/ants || (echo "ERROR: /opt/ants not found after install" && exit 1)

#########################
# Runtime with all libs #
#########################
FROM debian:bookworm-slim

ARG DEBIAN_FRONTEND
ARG FSL_VERSION=6.0.5.1
ARG FREESURFER_VERSION=7.4.1
ARG FREESURFER_TARBALL=freesurfer-linux-ubuntu22_amd64-${FREESURFER_VERSION}.tar.gz
ARG AFNI_TARBALL=linux_rocky_8.tgz

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      bc \
      bzip2 \
      ca-certificates \
      curl \
      dc \
      git \
      locales \
      netpbm \
      perl \
      python3 \
      python3-pip \
      python3-dev \
      python3-venv \
      tar \
      tcsh \
      wget \
      vim \
      bash-completion \
      openjdk-17-jdk \
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
      zlib1g && \
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
################
ENV FREESURFER_HOME=/usr/local/freesurfer
RUN curl -fsSL "https://surfer.nmr.mgh.harvard.edu/pub/dist/freesurfer/${FREESURFER_VERSION}/${FREESURFER_TARBALL}" -o /tmp/freesurfer.tar.gz && \
    tar --no-same-owner -xzvf /tmp/freesurfer.tar.gz -C /usr/local && \
    rm /tmp/freesurfer.tar.gz

##############
# Environment
##############
ENV ANTSPATH=/opt/ants/bin/ \
    FSLDIR=/usr/local/fsl \
    AFNI_HOME=/usr/local/afni \
    AFNIPATH=/usr/local/afni \
    FREESURFER_HOME=/usr/local/freesurfer \
    FS_LICENSE=/opt/freesurfer/license.txt \
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
    PYTHONPATH=/opt/banana/src

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
export PATH=$FSLDIR/bin:$AFNI_HOME:$ANTSPATH:$FREESURFER_HOME/bin:$PATH\n\
\n\
# License check\n\
if [ ! -f "$FS_LICENSE" ]; then\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "WARNING: FreeSurfer license not found at $FS_LICENSE"\n\
    echo "To run FreeSurfer tools, please mount your license file:"\n\
    echo "  docker run -it -v /path/to/license.txt:/opt/freesurfer/license.txt ..."\n\
    echo "--------------------------------------------------------------------------------"\n\
fi\n\
\n\
# Welcome Message\n\
if [ "$PS1" ]; then\n\
    echo "================================================================================"\n\
    echo "Welcome to banana Interactive Environment"\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "Installed Tools:"\n\
    echo "  - FSL:        \$(fslval 2>/dev/null | head -n 1 || echo \"Installed\")"\n\
    echo "  - ANTs:       \$(antsRegistration --version | grep Version | head -n 1 || echo \"Installed\")"\n\
    echo "  - AFNI:       \$(afni -version | head -n 1 || echo \"Installed\")"\n\
    echo "  - FreeSurfer: \$(cat \$FREESURFER_HOME/build-stamp.txt 2>/dev/null || echo \"Installed\")"\n\
    echo "  - Python:     \$(python3 --version)"\n\
    echo "  - Java:       \$(java -version 2>&1 | head -n 1)"\n\
    echo "  - uv:         \$(uv --version)"\n\
    echo "--------------------------------------------------------------------------------"\n\
    echo "Usage Examples:"\n\
    echo "  ./run_nextflow.sh run main.nf --bids_dir /data --output_dir /output --output_space \"NMT2Sym:res-1\""\n\
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

#################
# Project Install
#################
WORKDIR /opt/banana
COPY . /opt/banana

ENV VIRTUAL_ENV=/opt/venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Redirect caches to writable locations to support arbitrary UIDs
ENV MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONPYCACHEPREFIX=/tmp/pycache

RUN mkdir -p /opt/banana/tmp /tmp/matplotlib /tmp/pycache && \
    TMPDIR=/opt/banana/tmp uv venv $VIRTUAL_ENV && \
    TMPDIR=/opt/banana/tmp uv pip install --no-cache -e /opt/banana && \
    rm -rf /opt/banana/tmp && \
    chown -R neuro:neuro /opt/banana $VIRTUAL_ENV && \
    chmod -R 777 /tmp/matplotlib /tmp/pycache /home/neuro

USER neuro
WORKDIR /home/neuro
CMD ["/bin/bash"]
