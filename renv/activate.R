# Hand-written minimal stub (Phase 0): renv is not installed on this host, so
# renv::init() has not run. This activates the project library if present and
# otherwise no-ops, so sourcing .Rprofile never errors. Once renv is available,
# run renv::init() (or renv::restore()) to replace this with the real script.
local({
  lib <- file.path("renv", "library")
  if (dir.exists(lib)) {
    .libPaths(c(normalizePath(lib, mustWork = FALSE), .libPaths()))
  }
  invisible(NULL)
})
