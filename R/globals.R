# Declare data.table's non-standard-evaluation symbols and the column names used
# across modules, so static checks do not flag them as undefined.
utils::globalVariables(c(
  ":=", ".", ".SD",
  "region", "iso3", "variable", "value", "year", "scenario", "model", "unit",
  "age_lower", "bin", "gdp_bn", "pop_mn",
  "age0to4", "age5to64", "age65plus",
  "rgdpe", "pop", "countrycode", "gdppc", "type", "era",
  "pop0to4", "pop5to64", "pop65plus", "gdppc_raw0",
  "pop_nat", "gdppc_nat", "gdppc_ref", "gdppc_pwt",
  "growth_ref", "growth_pwt", "ratio", "pct_diff", "flag",
  "share_0_4", "share_5_64", "share_65plus",
  "s0_4", "s5_64", "s65", "diff_0_4", "diff_5_64", "diff_65plus",
  "pop_wpp", "pop_ssp",
  "gdppc_w", "gdppc_a", "zero_pop", "num", "pop_wtd_density",
  "gdppc_natavg", "gdppc_adm0",
  "kummu_ir", "kummu_nat", "pwt", "pop_base", "g_pwt", "g_ssp", "gval",
  "growth", "gdppc_2023", "g", "base", "b25", "gf", "g25", "g30", "gann",
  "nat", "p22", "p23", "s22", "s23", "i.gval",
  "ghs_ir", "ghs_nat", "ssp_nat", "share",
  "pop_total", "share_0_4", "share_5_64", "share_65plus", "knot",
  "gser", "gsm", "area_km2", "pop_density"
))
