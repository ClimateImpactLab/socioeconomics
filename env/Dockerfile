# Container image for the CIL 2.0 (irpanel) pipeline.
# Built from micromamba and the version-locked conda environment, so the R
# 4.4.3 stack (data.table, targets, terra/sf) matches the working conda env
# exactly and reproduces the same panel. The previous rocker/geospatial:4.2.2
# base gave R 4.2.2 and broke data.table/targets, so it is no longer used.
#
# Build from the repo root so the env file and project copy resolve:
#   docker build -f env/Dockerfile -t irpanel .
FROM mambaorg/micromamba:2.0.5

# Build the environment from the locked versions. Strip the absolute name and
# prefix from the lock file so it installs into a fixed in-image prefix.
COPY --chown=$MAMBA_USER:$MAMBA_USER env/environment-lock.yml /tmp/environment-lock.yml
RUN sed -e '/^name:/d' -e '/^prefix:/d' /tmp/environment-lock.yml > /tmp/env.yml \
 && micromamba create -y -n irpanel -f /tmp/env.yml \
 && micromamba clean -a -y

# Activate the env for every following RUN and for CMD.
ARG MAMBA_DOCKERFILE_ACTIVATE=1
ENV ENV_NAME=irpanel

WORKDIR /irpanel
COPY . /irpanel

# Build the panel in a single process. callr_function = NULL keeps targets from
# spawning a worker process, which the RCC compute nodes do not allow.
CMD ["Rscript", "-e", "targets::tar_make(callr_function = NULL)"]
