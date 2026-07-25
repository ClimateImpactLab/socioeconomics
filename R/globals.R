# Declare data.table's non-standard-evaluation symbols and the column names used
# across modules, so static checks do not flag them as undefined.
utils::globalVariables(c(
  ":=", ".", ".SD",
  "region", "iso3", "variable", "value", "year", "scenario", "model", "unit",
  "age_lower", "bin", "gdp_bn", "pop_mn",
  "age0to4", "age5to64", "age65plus",
  "rgdpe", "pop", "countrycode", "gdppc", "type", "era",
  "pop0to4", "pop5to64", "pop65plus", "gdppc_raw", "gdppc_raw0",
  "ratio", "pct_diff", "gdppc_natavg", "gdppc_adm0",
  "gdppc_w", "gdppc_a", "zero_pop", "num", "pop_wtd_density",
  "kummu_ir", "kummu_nat", "pwt", "pop_base", "g_pwt", "g_ssp", "gval",
  "growth", "gdppc_2023", "g", "base", "b25", "gf", "g25", "g30", "gann",
  "nat", "p22", "p23", "s22", "s23", "i.gval",
  "ghs_ir", "ghs_nat", "ssp_nat", "share",
  "pop_total", "share_0_4", "share_5_64", "share_65plus", "knot",
  "gser", "gsm", "area_km2", "pop_density"
))
