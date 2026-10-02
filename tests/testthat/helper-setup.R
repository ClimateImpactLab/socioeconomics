# Shared setup for the io and validate tests: find the repo, load the track
# config, and source the reader and validation modules into the calling
# environment. The source path is made absolute; ir_shapes and benchmark keep
# their config paths. IRPANEL_CONFIG picks the config; the default is the
# book-reproduction track.

find_repo_root <- function() {
  d <- normalizePath(getwd())
  for (i in 1:6) {
    if (file.exists(file.path(d, "_targets.R")) &&
        file.exists(file.path(d, "R", "io.R"))) {
      return(d)
    }
    d <- dirname(d)
  }
  NULL
}

io_setup <- function(env = parent.frame()) {
  skip_if_not(requireNamespace("yaml", quietly = TRUE))
  skip_if_not(requireNamespace("data.table", quietly = TRUE))
  root <- find_repo_root()
  skip_if(is.null(root), "repo root not found")
  cfg_path <- Sys.getenv("IRPANEL_CONFIG",
                         file.path("configs", "climate-compensation.yml"))
  if (!grepl("^(/|[A-Za-z]:)", cfg_path)) {
    cfg_path <- file.path(root, cfg_path)
  }
  cfg <- yaml::read_yaml(cfg_path)
  cfg$paths$source <- file.path(root, cfg$paths$source)
  sys.source(file.path(root, "R", "io.R"), envir = env)
  sys.source(file.path(root, "R", "validate.R"), envir = env)
  cfg
}
