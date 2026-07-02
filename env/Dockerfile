# Container image for the CIL 2.0 pipeline.
# rocker/geospatial ships R + terra/sf/GDAL/GEOS/PROJ preinstalled; we pin the
# remaining R deps via renv restore for reproducibility.
FROM rocker/geospatial:4.2.2

WORKDIR /irpanel

# renv restore: copy the lockfile first for layer caching.
COPY renv.lock renv.lock
COPY .Rprofile .Rprofile
COPY renv/activate.R renv/activate.R

RUN R -e "install.packages('renv', repos='https://cloud.r-project.org')" \
 && R -e "renv::restore()"

# Copy the rest of the project.
COPY . /irpanel

CMD ["R", "-e", "targets::tar_make()"]
