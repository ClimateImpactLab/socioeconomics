# Tests for R/write_outputs.R. The Zarr writer shells out to Python, so the
# full round-trip runs where a Python with zarr is available (the cluster);
# here the R-side contract is tested with a stubbed interpreter.

test_that("resolve_python honors PYTHON and falls back to the PATH", {
  root <- find_repo_root()
  sys.source(file.path(root, "R", "io.R"), envir = environment())

  withr::local_envvar(PYTHON = "/no/such/interpreter")
  # An unusable override is skipped in favor of the PATH interpreters.
  expect_true(resolve_python() %in% c("python3", "python"))

  fake <- file.path(tempdir(), "fake_py")
  file.create(fake)
  withr::local_envvar(PYTHON = fake)
  expect_equal(resolve_python(), fake)
})

test_that("write_zarr builds the store path and fails loudly on error", {
  root <- find_repo_root()
  sys.source(file.path(root, "R", "io.R"), envir = environment())
  sys.source(file.path(root, "R", "write_outputs.R"), envir = environment())
  cfg <- list(paths = list(output = tempdir()))

  # A fake interpreter that records its arguments and succeeds.
  fake <- file.path(tempdir(), "fake_python.sh")
  writeLines(c("#!/bin/sh", "echo \"$@\" > \"$0.args\"", "exit 0"), fake)
  Sys.chmod(fake, "0755")
  withr::local_envvar(PYTHON = fake)

  out <- write_zarr(cfg, c("a.csv", "b.csv"))
  expect_equal(out, file.path(tempdir(), "ir_combined.zarr"))
  args <- readLines(paste0(fake, ".args"))
  expect_match(args, "panels_to_zarr.py")
  expect_match(args, "a.csv b.csv")

  # A failing interpreter propagates as an R error.
  writeLines(c("#!/bin/sh", "exit 3"), fake)
  expect_error(write_zarr(cfg, "a.csv"), "status 3")
})
