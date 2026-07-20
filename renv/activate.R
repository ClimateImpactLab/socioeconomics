# Minimal stub: renv is not installed here, so renv::init() has not run. This
# adds the project library to the path if it exists and otherwise does nothing,
# so sourcing .Rprofile never errors. Once renv is available, run renv::init()
# (or renv::restore()) to replace this with the real script.
local({
  lib <- file.path("renv", "library")
  if (dir.exists(lib)) {
    .libPaths(c(normalizePath(lib, mustWork = FALSE), .libPaths()))
  }
  invisible(NULL)
})
