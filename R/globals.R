# Declare data.table's non-standard-evaluation symbols and the column names used
# across modules, so static checks do not flag them as undefined.
utils::globalVariables(c(
  ":=", ".", ".SD",
  "region", "iso3", "variable", "value", "year", "scenario", "model", "unit",
  "age_lower", "bin", "gdp_bn", "pop_mn",
  "age0to4", "age5to64", "age65plus"
))
