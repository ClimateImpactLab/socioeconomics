# Fetch or verify the raw inputs listed in data/manifest.yml. Run from the
# repo root.
#
# fetch: auto   -> download (or extract from an archive) into the source dir
#                  if the file is missing, then check its md5.
# fetch: manual -> never download; only check the file, and if it is missing
#                  tell the user where to get it.
# fetch: script -> never download; only check the file, and if it is missing
#                  name the script that reproduces it.
#
# Any md5 mismatch, and any missing manual or script file, is fatal. Nothing
# outside the source dir is touched. A per-file summary is printed before any
# error is raised.

library(tools)  # md5sum

`%||%` <- function(a, b) if (is.null(a)) b else a

md5_of <- function(path) unname(tools::md5sum(path))

download_to <- function(url, dest) {
  ok <- tryCatch(
    {
      utils::download.file(url, dest, mode = "wb", quiet = FALSE)
      TRUE
    },
    error = function(e) {
      message("  download failed: ", conditionMessage(e))
      FALSE
    }
  )
  ok && file.exists(dest)
}

# Extract one member from a zip to dest. member may be an explicit path inside
# the zip, or NULL to match the single entry whose basename equals dest's.
extract_member <- function(zip_path, member, dest) {
  listing <- utils::unzip(zip_path, list = TRUE)$Name
  if (is.null(member)) {
    hit <- listing[basename(listing) == basename(dest)]
    if (length(hit) != 1) {
      message("  could not find a unique '", basename(dest), "' in the archive")
      return(FALSE)
    }
    member <- hit
  } else if (!member %in% listing) {
    message("  archive does not contain member ", member)
    return(FALSE)
  }
  tmp <- tempfile("extract_")
  dir.create(tmp)
  on.exit(unlink(tmp, recursive = TRUE), add = TRUE)
  utils::unzip(zip_path, files = member, exdir = tmp)
  file.copy(file.path(tmp, member), dest, overwrite = TRUE)
  file.exists(dest)
}

# Put an auto file in place if it is missing. Archive entries are downloaded
# as a zip (verified if the archive md5 is pinned) and one member extracted.
obtain_auto <- function(f, dest) {
  if (file.exists(dest)) return(invisible())
  dir.create(dirname(dest), showWarnings = FALSE, recursive = TRUE)
  if (!is.null(f$archive)) {
    zip_tmp <- tempfile(fileext = ".zip")
    on.exit(unlink(zip_tmp), add = TRUE)
    message("  fetching archive ", f$archive$url)
    if (!download_to(f$archive$url, zip_tmp)) return(invisible())
    if (!is.null(f$archive$md5) && md5_of(zip_tmp) != f$archive$md5) {
      stop("archive md5 mismatch while fetching ", f$path)
    }
    extract_member(zip_tmp, f$archive$member, dest)
  } else {
    message("  downloading ", f$url)
    download_to(f$url, dest)
  }
  invisible()
}

# Verify one file that is expected to exist. Returns a status string.
verify <- function(f, dest) {
  if (!file.exists(dest)) {
    switch(f$fetch %||% "auto",
           manual = "missing (manual)",
           script = "missing (script)",
           "missing (auto)")
  } else if (md5_of(dest) != f$md5) {
    "mismatch"
  } else {
    "ok"
  }
}

main <- function(manifest_path = "data/manifest.yml") {
  manifest <- yaml::read_yaml(manifest_path)
  source_dir <- normalizePath(manifest$source_dir, mustWork = FALSE)
  message("Source dir: ", source_dir, "\n")

  results <- list()
  for (src in manifest$sources) {
    for (f in src$files) {
      dest <- file.path(source_dir, f$path)
      message(f$path)
      if (identical(f$fetch, "auto")) obtain_auto(f, dest)
      results[[f$path]] <- list(f = f, status = verify(f, dest))
    }
  }

  message("\nSummary:")
  bad <- character()
  for (path in names(results)) {
    st <- results[[path]]$status
    message(sprintf("  %-52s %s", path, st))
    if (st != "ok") bad <- c(bad, path)
  }

  if (length(bad) > 0) {
    message("\nAction needed:")
    for (path in bad) {
      r <- results[[path]]
      if (r$status == "mismatch") {
        message("  ", path,
                ": md5 does not match the manifest; re-download or check it.")
      } else if (identical(r$f$fetch, "manual")) {
        msg <- r$f$instructions %||% "download from the source and place here."
        message("  ", path, ": ", msg)
      } else if (identical(r$f$fetch, "script")) {
        script <- r$f$script %||% "the fetch script"
        message("  ", path,
                ": file missing -- reproduce it by running ", script)
      } else {
        url <- r$f$url %||% r$f$archive$url
        message("  ", path, ": automatic fetch failed; download from ", url)
      }
    }
    stop(length(bad), " input(s) not ready; see messages above.")
  }

  message("\nAll inputs present and verified.")
  invisible(TRUE)
}

if (sys.nframe() == 0) main()
