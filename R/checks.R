# Hard assertions on the final panel. Runs before the writers so tar_make()
# halts on any violation. Each check appends a pass/fail record with enough
# detail to locate the offending IRs or countries; check_panel prints the
# summary and stops if anything failed.

N_IR <- 24378L
YEARS <- 1981:2100
PANEL_COLS <- c("hierid", "iso3", "year", "gdppc", "gdppc_raw", "gdppc_raw0",
                "gdp", "pop", "area_km2", "pop_density", "pop_wtd_density",
                "pop0to4", "pop5to64", "pop65plus")

# One check record: ok plus a short locator detail for failures.
chk <- function(results, name, ok, detail = "") {
  results[[name]] <- list(ok = isTRUE(ok), detail = detail)
  results
}

print_and_stop_on_failure <- function(results, label) {
  failed <- names(results)[!vapply(results, `[[`, TRUE, "ok")]
  for (name in names(results)) {
    r <- results[[name]]
    status <- if (r$ok) "PASS" else "FAIL"
    message(sprintf("[%s] %s %s%s", label, status, name,
                    if (nzchar(r$detail)) paste0(": ", r$detail) else ""))
  }
  if (length(failed) > 0) {
    stop("panel checks failed (", label, "): ",
         paste(failed, collapse = ", "))
  }
  invisible(results)
}

#' Assert the panel's invariants before writing.
#'
#' @param panel Output of postprocess_panel().
#' @param config Parsed config.yml list.
#' @param scen SSP scenario the panel was built for.
#' @param gdp_model GDP model the panel was built for.
#' @return checks report, invisibly, on success; stops on any failure.
check_panel <- function(panel, config, scen = "SSP3", gdp_model = "IIASA") {
  p <- data.table::as.data.table(panel)
  res <- list()

  # Structural: full IR x year grid, the exact column set, no duplicates.
  res <- chk(res, "columns", identical(colnames(p), PANEL_COLS),
             paste(setdiff(PANEL_COLS, colnames(p)), collapse = ", "))
  res <- chk(res, "grid_size", nrow(p) == N_IR * length(YEARS),
             sprintf("%d rows, expected %d", nrow(p),
                     N_IR * length(YEARS)))
  res <- chk(res, "ir_count", data.table::uniqueN(p$hierid) == N_IR,
             sprintf("%d IRs", data.table::uniqueN(p$hierid)))
  res <- chk(res, "year_span", identical(sort(unique(p$year)), YEARS),
             sprintf("%d-%d", min(p$year), max(p$year)))
  dup <- p[, .N, by = .(hierid, year)][N > 1]
  res <- chk(res, "no_duplicates", nrow(dup) == 0,
             paste(head(dup$hierid, 3), collapse = ", "))

  # NA contract: only gdppc_raw / gdppc_raw0 may be NA, and only where the
  # pipeline deliberately puts them: raw0 exactly before 1990; raw before
  # 1990 everywhere and, from 1990 on, only for zero-income IRs (gdppc
  # filled to 0) or before a late-entering source country's first data year
  # (SSD enters Kummu in 2008, CUW in 2005; their earlier years are imputed).
  never_na <- c("gdppc", "gdp", "pop", "area_km2", "pop_density",
                "pop_wtd_density", "pop0to4", "pop5to64", "pop65plus")
  na_counts <- vapply(never_na, function(cl) sum(is.na(p[[cl]])), 0L)
  res <- chk(res, "no_unexpected_na", all(na_counts == 0),
             paste(names(na_counts)[na_counts > 0], collapse = ", "))
  res <- chk(res, "raw0_na_iff_pre1990",
             identical(is.na(p$gdppc_raw0), p$year < 1990))
  first_raw <- p[!is.na(gdppc_raw), .(first_year = min(year)), by = hierid]
  bad_raw <- merge(p[year >= 1990 & is.na(gdppc_raw) & gdppc != 0],
                   first_raw, by = "hierid", all.x = TRUE)
  bad_raw <- bad_raw[is.na(first_year) | year >= first_year]
  res <- chk(res, "raw_na_only_deliberate", nrow(bad_raw) == 0,
             paste(head(unique(bad_raw$hierid), 3), collapse = ", "))

  # Ranges. The gdppc band is generous on purpose: it catches unit mistakes
  # (millions vs persons, cents vs dollars), not distributional drift.
  res <- chk(res, "gdppc_band",
             p[, all(gdppc >= 0 & gdppc < 1e7)],
             sprintf("range %.3g to %.3g", min(p$gdppc), max(p$gdppc)))
  neg <- vapply(c("pop", "pop0to4", "pop5to64", "pop65plus", "area_km2"),
                function(cl) sum(p[[cl]] < 0), 0L)
  res <- chk(res, "non_negative", all(neg == 0),
             paste(names(neg)[neg > 0], collapse = ", "))
  # The SSP age bins do not sum exactly to the SSP total population (the
  # observed ratio floor in the source is ~0.989), so the cohort sum is a
  # band check: it catches a dropped or double-counted bin, not source slack.
  bad_cs <- p[pop > 0][
    (pop0to4 + pop5to64 + pop65plus) / pop < 0.97 |
      (pop0to4 + pop5to64 + pop65plus) / pop > 1.03]
  res <- chk(res, "cohorts_sum_to_pop", nrow(bad_cs) == 0,
             paste(head(unique(bad_cs$hierid), 3), collapse = ", "))
  bad_gdp <- p[abs(gdp - gdppc * pop) > pmax(1e-9 * abs(gdp), 1e-9)]
  res <- chk(res, "gdp_is_gdppc_times_pop", nrow(bad_gdp) == 0,
             paste(head(unique(bad_gdp$hierid), 3), collapse = ", "))

  # Delta invariants, active only when the corresponding toggle is on.
  if (identical(config$deltas$pop_control, "UN_WPP")) {
    h <- config$deltas$pop_handoff_year
    if (is.null(h)) h <- 2023L
    wpp <- read_wpp(config)
    sums <- p[, .(ir_sum = sum(pop)), by = .(iso3, year)]

    # Through the handoff year the national sums match UN WPP.
    w <- merge(sums[year <= h], wpp[, .(iso3, year, wpp_nat = pop * 1e6)],
               by = c("iso3", "year"))
    bad_w <- w[abs(ir_sum - wpp_nat) > 1e-6 * wpp_nat]
    res <- chk(res, "pop_sums_to_wpp", nrow(bad_w) == 0,
               paste(head(unique(bad_w$iso3), 3), collapse = ", "))

    # After the handoff the sums follow the scenario trajectory rebased to
    # the WPP handoff level -- WPP(h) * SSP(t) / SSP(h) -- for countries with
    # an SSP trajectory, and stay on WPP for the rest. Recomputed from the
    # raw readers rather than taken from build_population.
    ssp_ann <- pop_linear_annual(
      read_ssp(config)$pop[era == "projection" & scenario == scen,
                           .(iso3, year, nat = pop)])
    anchor <- merge(ssp_ann[year == h & nat > 0, .(iso3, ssp_h = nat)],
                    wpp[year == h & pop > 0, .(iso3, wpp_h = pop)],
                    by = "iso3")
    expected <- rbind(
      merge(ssp_ann[year > h], anchor,
            by = "iso3")[, .(iso3, year, exp_nat = wpp_h * nat / ssp_h * 1e6)],
      wpp[year > h & !iso3 %in% anchor$iso3,
          .(iso3, year, exp_nat = pop * 1e6)]
    )
    r2 <- merge(sums, expected, by = c("iso3", "year"))
    bad_r <- r2[abs(ir_sum - exp_nat) > 1e-6 * exp_nat]
    res <- chk(res, "pop_rebased_ssp_after_handoff", nrow(bad_r) == 0,
               paste(head(unique(bad_r$iso3), 3), collapse = ", "))

    # No jump at the handoff: the growth into h+1 equals the control
    # trajectory's own growth (the rebase pins the level at h, so the only
    # growth crossing the seam is the SSP's -- or WPP's for countries with no
    # SSP trajectory). Implied by the two sum checks; kept as an explicit
    # contract on the seam.
    seam <- merge(sums[year == h, .(iso3, at_h = ir_sum)],
                  sums[year == h + 1L, .(iso3, at_h1 = ir_sum)], by = "iso3")
    seam <- merge(seam, wpp[year == h & pop > 0,
                            .(iso3, c_h = pop * 1e6)], by = "iso3")
    seam <- merge(seam, expected[year == h + 1L,
                                 .(iso3, c_h1 = exp_nat)], by = "iso3")
    bad_j <- seam[abs(at_h1 / at_h - c_h1 / c_h) > 1e-6 * (c_h1 / c_h)]
    res <- chk(res, "pop_no_jump_at_handoff", nrow(bad_j) == 0,
               paste(head(unique(bad_j$iso3), 3), collapse = ", "))
  }
  if (isTRUE(config$deltas$force_gdp_sum)) {
    # Checked on raw income: the Bartlett smoothing blends 2024-2035 in the
    # smoothed gdppc, so the exact constraint lives in gdppc_raw0 * pop.
    ssp_gdppc <- read_ssp(config)$gdppc[scenario == scen]
    nat <- interp_annual(ssp_gdppc[model == gdp_model, .(iso3, year, gdppc)])
    nat <- nat[year >= 2024,
               .(iso3, year, nat_gdppc = gdppc * KUMMU_TO_2005)]
    sums <- p[, .(ir_gdp = sum(gdppc_raw0 * pop), pop_nat = sum(pop)),
              by = .(iso3, year)]
    g <- merge(sums, nat, by = c("iso3", "year"))
    tol <- config$tolerances$gdp_sum_pct / 100
    bad_g <- g[abs(ir_gdp - nat_gdppc * pop_nat) >
                 tol * abs(nat_gdppc * pop_nat)]
    res <- chk(res, "gdp_sums_to_national", nrow(bad_g) == 0,
               paste(head(unique(bad_g$iso3), 3), collapse = ", "))
  }

  print_and_stop_on_failure(res, paste0(scen, "/", gdp_model))
}

#' Assert the cross-panel invariants over all combinations.
#'
#' @param panels Named list of panels, names like "SSP2_OECD".
#' @param config Parsed config.yml list (for the population handoff year).
#' @return checks report, invisibly, on success; stops on any failure.
check_cross_panel <- function(panels, config) {
  res <- list()
  panels <- lapply(panels, function(p) {
    data.table::as.data.table(p)[order(hierid, year)]
  })
  scens <- unique(sub("_.*", "", names(panels)))

  # Population is model-independent within a scenario.
  for (sc in scens) {
    members <- panels[grep(paste0("^", sc, "_"), names(panels))]
    same <- length(members) < 2 ||
      all(vapply(members[-1], function(p) {
        identical(p$pop, members[[1]]$pop)
      }, logical(1)))
    res <- chk(res, paste0("pop_model_independent_", sc), same)
  }

  # Area is identical across every combination.
  same_area <- all(vapply(panels[-1], function(p) {
    identical(p$area_km2, panels[[1]]$area_km2)
  }, logical(1)))
  res <- chk(res, "area_identical", same_area)

  # Scenarios must diverge after the population handoff: two SSPs with
  # identical post-handoff population would mean the scenario trajectory
  # never entered the controls. Skipped when a panel has no post-handoff
  # years (synthetic test grids) or a model has a single scenario.
  h <- config$deltas$pop_handoff_year
  if (is.null(h)) h <- 2023L
  for (gm in unique(sub("^.*_", "", names(panels)))) {
    members <- panels[grep(paste0("_", gm, "$"), names(panels))]
    if (length(members) < 2 || nrow(members[[1]][year > h]) == 0) next
    post <- lapply(members, function(p) p[year > h, pop])
    pairs <- utils::combn(length(members), 2)
    same <- apply(pairs, 2, function(ix) {
      identical(post[[ix[1]]], post[[ix[2]]])
    })
    res <- chk(res, paste0("pop_differs_across_scenarios_", gm), !any(same),
               paste(names(members)[unique(as.vector(
                 pairs[, same, drop = FALSE]))], collapse = ", "))
  }

  print_and_stop_on_failure(res, "cross-panel")
}
