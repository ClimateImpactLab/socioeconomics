# Serialize the final panel. Both writers depend on the checks node, so nothing
# is written for a panel that failed its contracts.

#' Write the panel to NetCDF, one file per scenario and GDP model.
#'
#' @param panel Output of postprocess_panel().
#' @param config Parsed config.yml list.
#' @param checks Result of check_panel(); dependency gate.
#' @return written file paths, invisibly.
write_netcdf <- function(panel, config, checks) {
  stop("not implemented")
}

#' Write a long-format CSV mirror of the panel.
#'
#' @param panel Output of postprocess_panel().
#' @param config Parsed config.yml list.
#' @param checks Result of check_panel(); dependency gate.
#' @return written file paths, invisibly.
write_csv_mirror <- function(panel, config, checks) {
  stop("not implemented")
}
