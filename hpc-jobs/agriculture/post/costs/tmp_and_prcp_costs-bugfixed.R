################################################
# GENERATE ADAPTATION COST CURVES
# MODIFIED FOR AG FROM THE MORTALITY
# MORTALITY SCRIPT. 

# Here we directly compute the "marginals" terms 
# that, for mortality, are calculated by the projection 
# system. This reduces the compute resource load 
# of ag projections, which is otherwise substantial.

# 5/2/2019


################################################



#### Clipping: Clipped portions of the response function do not contribute to adaptation costs.

#### Crop-specific configurations are set in ag_costs_config.R and read-in here.

# (Legacy mortality code note) 04/25/2018: This version checks whether timesteps 
# in the climate file are equivalent to timesteps in the impacts file. Assumption: the impacts file always 
# has 120 time steps (i.e. goes to year 2100) while the climate file may have < 120 time steps (e.g. up to year 2099 or 2098)
# If found unequal, this code removes the last n columns in the impacts file corresponding to the difference in years



###############################################


# Syntax (bash): 
# Rscript tmp_and_prcp_costs.R $crop 13 $seed $wd $model $rcp $ssp $iam


# $crop: the crop as a string (e.g. 'maize')
# 13:    the averaging period for the income covariate Bartlett kernel. This should not change.
# $seed: seed value for a Monte Carlo draw (if not calculating MC costs, set <seed> to 'unused')
# $wd : the directory in which the projection output is stored, with the 'batch' folder appended ('median', or 'montecarlo/batch{i}'...)
# $model:    climate model (gcm name as a string)
# $r:    rcp 
# $s:    ssp
# $i:    "iam" ('high' or 'low')


###############################################


rm(list=ls())

list.of.packages <- c('pracma','ncdf4','abind','matrixStats','reticulate','stringr')
new.packages <- list.of.packages[!(list.of.packages %in% installed.packages()[,"Package"])]
if(length(new.packages)) install.packages(new.packages, repos = "http://cran.us.r-project.org")
invisible(lapply(list.of.packages, function(x) library(x, character.only=TRUE)))
require(dplyr)

###############################################


exclude.rice.tmin.costs <- FALSE
encode_regions <- TRUE # to add an 'ascii' encoding attribute to the region dimension (compatibility with Python netcdf4 package)

args <- commandArgs(trailingOnly=T)

if (length(args)!=8) stop('not enough arguments passed to tmp_and_prcp_costs.R')

crop <- args[1]
avg.period <- args[2]
seed <- args[3] # seed value for a Monte Carlo draw (if not calculating MC costs, set <seed> to 'unused')
wd <- args[4]
model <- args[5]
rcp <- as.numeric(str_extract(args[6],"[[:digit:]]+"))
ssp <- as.numeric(str_extract(args[7],"[[:digit:]]+"))
iam <- args[8]



# checking seed 
stopifnot(is.character(seed))
if(seed!='unused'){ # no sampling
  numbers_only <- function(x) !grepl("\\D", x)
  if(!numbers_only(seed) | (nchar(seed)>1 & substr(seed,1,1)=='0')){ # can't coerce to integer 
    stop(paste0("the parameter <seed> should be either equal to 'unused' if not sampling, or only made coercible to an integer. You passed : ", seed))
  } 
}


# here I am trying to retrieve the absolute path to this executed script 
# this is just giving you the first command line argument you passed to 'Rscript' -- you might have given the absolute OR relative path to this code
exec_path <- dirname(gsub('--file=', '', commandArgs()[grepl('--file=',commandArgs())])) 
stopifnot(is.character(exec_path)) # you want a character
stopifnot(nchar(exec_path)>=1) # and it should be at least '.'
# you ran the code from where it's located (i.e you typed Rscript tmp_and_prcp_costs.R)
if(exec_path=='.'){
  exec_path = getwd()
} else if(substr(exec_path,1,1)=='/'){ # you ran the code with its absolute path, so it starts with '/'. This works only in Unix systems or macOS. 
  exec_path = exec_path # absolute path works fine ! 
} else { # somewhere in between ! 
  exec_path = file.path(getwd(), exec_path)
}

configpath <- file.path(exec_path, 'ag_costs_config.R')

setwd(wd)

root <- "/project"

# Income folder is set by the job, so a run never falls back to the old income silently
incdir <- Sys.getenv('AG_INCOME_DIR')
if (incdir == '') stop('AG_INCOME_DIR is not set')
incpath <- paste0(incdir, '/SSP', ssp, '_IAM-', iam, '_', avg.period, 'yr-avg.nc4')
print(paste0('income file is: ', incpath))
irrpath <- paste0(root,'/cil/sacagawea_shares/gcp/social/baselines/agriculture/income_netcdfs/irrigation_share.nc4')
tavgpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '_seasonaltasmax.nc4')
pavgpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '_seasonalpr.nc4')
ddpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '_seasonaledd.nc4')
prpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '_monthbinpr.nc4')
                 
outpath <- paste0('rcp', rcp, '/', model, '/', iam, '/SSP', ssp)
print(paste0('outpath is: ', outpath, '/adaptation_costs.nc4'))

if ((crop == 'rice') | (crop == 'wheat-spring')) {
  tminpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '_seasonaltasmin.nc4')
}

if (crop == 'wheat-winter') {
  # Winter wheat has all its own weather paths, due to the fall/winter/summer seasons.
  
  # # Tavg and Pavg are the same for all seasons by definition, so just load the summer copy of the file.
  tavgpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-summer_seasonaltasmax.nc4')
  pavgpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-summer_seasonalpr.nc4')
  
  # For winter wheat, the season without a season name appended (to mirror other crops) is spring/summer.
  ddpath.fall <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-fall_seasonaledd.nc4')
  ddpath.wint <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-winter_seasonaledd.nc4')
  ddpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-summer_seasonaledd.nc4')
  
  prpath.fall <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-fall_monthbinpr.nc4')
  prpath.wint <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-winter_monthbinpr.nc4')
  prpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-summer_monthbinpr.nc4')
  
  tminpath.wint <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-winter_seasonaltasmin.nc4')
  tminpath <- paste0(root,'/cil/kupe_shares/CIL_temp_storage/agriculture/impacts-mealy/climate-mealy/explicit_rolling_year_v1.8edd/rcp', rcp,'/', model,'/', crop, '-summer_seasonaltasmin.nc4')
}


# Load crop-specific configurations for costs
source(configpath)




#####################


print('------------------')
print(paste0('Calculating costs for ', crop, ' under model ', model, ' / RCP ', rcp, ' / SSP', ssp, ' / IAM-',iam))
print('------------------')


##############################################################################################
# LOAD realized climate variable from single folder
##############################################################################################


# Read in income and irrigation netcdfs
nc.inc <- nc_open(incpath)
inc.array <- ncvar_get(nc.inc, 'loggdppc')
nc.irr <- nc_open(irrpath)
irr.array <- ncvar_get(nc.irr, 'irrigation')

rownames(inc.array) <- ncvar_get(nc.inc, 'regions')
colnames(inc.array) <- ncvar_get(nc.inc, 'year')
rownames(irr.array) <- ncvar_get(nc.irr, 'regions')
colnames(irr.array) <- ncvar_get(nc.irr, 'year')





## Open the weather and climate netcdfs
# Note: winter wheat has a separate data structure for weather data, but not for covariates (including climate covariates).
nc.tavg <- nc_open(tavgpath)
nc.pavg <- nc_open(pavgpath)
temps.avg <- ncvar_get(nc.tavg, 'averaged') #average temperatures
prcps.avg <- ncvar_get(nc.pavg, 'averaged') #average temperatures
regions.tavg <- ncvar_get(nc.tavg, 'regions')
regions.pavg <- ncvar_get(nc.pavg, 'regions')
year.tavg <- ncvar_get(nc.tavg, 'year')
year.pavg <- ncvar_get(nc.pavg, 'year')

if (crop != 'wheat-winter') {
  # Winter wheat has a separate weather data structure.
  # Load weather terms for non-winter-wheat crops. They are created with the average temps and have the same region and year indexing. 
  # Only include tmin if the crop is rice or spring wheat.
  nc.dd <- nc_open(ddpath)
  nc.pr <- nc_open(prpath)
  dd.yr <- ncvar_get(nc.dd, 'annual') # 'annual' 'averaged'
  pr.yr <- ncvar_get(nc.pr, 'annual') # 'annual' 'averaged'
  
  if ((crop == 'rice') | (crop == 'wheat-spring')) {
    if(!exclude.rice.tmin.costs) {
      nc.tmin <- nc_open(tminpath)
      tmin.yr <- ncvar_get(nc.tmin, 'annual') # 'annual' 'averaged'
      year.tmin <- ncvar_get(nc.tmin, 'year')
      regions.tmin <- ncvar_get(nc.tmin, 'regions')
    } else {
      tmin.yr <- dd.yr[1,,] * 0
      year.tmin <- year.tavg
      regions.tmin <- regions.tavg
    }
  } else {
    # Other crops don't use tmin, so set it to an array of zeros and it will drop out everywhere.
    tmin.yr <- dd.yr[1,,] * 0
    year.tmin <- ncvar_get(nc.tavg, 'year')
    regions.tmin <- ncvar_get(nc.tavg, 'regions')
  }
  
} else {
  # The crop is winter wheat. Winter wheat has a separate weather data structure due to fall/winter/summer seasons.
  # For winter wheat, the season without a season name appended (to mirror other crops) is spring/summer.
  nc.dd.fall <- nc_open(ddpath.fall)
  nc.dd.wint <- nc_open(ddpath.wint)
  nc.dd <- nc_open(ddpath)
  nc.pr.fall <- nc_open(prpath.fall)
  nc.pr.wint <- nc_open(prpath.wint)
  nc.pr <- nc_open(prpath)
  dd.yr.fall <- ncvar_get(nc.dd.fall, 'annual') # 'annual' 'averaged'
  dd.yr.wint <- ncvar_get(nc.dd.wint, 'annual') # 'annual' 'averaged'
  dd.yr <- ncvar_get(nc.dd, 'annual') # 'annual' 'averaged'
  pr.yr.fall <- ncvar_get(nc.pr.fall, 'annual') # 'annual' 'averaged'
  pr.yr.wint <- ncvar_get(nc.pr.wint, 'annual') # 'annual' 'averaged'
  pr.yr <- ncvar_get(nc.pr, 'annual') # 'annual' 'averaged'
  
  nc.tmin.wint <- nc_open(tminpath.wint)
  nc.tmin <- nc_open(tminpath)
  tmin.yr.wint <- ncvar_get(nc.tmin.wint, 'annual') # 'annual' 'averaged'
  tmin.yr <- ncvar_get(nc.tmin, 'annual') # 'annual' 'averaged'
  year.tmin <- ncvar_get(nc.tmin, 'year')
  regions.tmin <- ncvar_get(nc.tmin, 'regions')
}



## Data Validation
# Make sure indexing is consistent between pavg and tavg
if ( isTRUE(all.equal(year.pavg, year.tavg)) ) {
  year.avg <- year.tavg
  rm(year.tavg, year.pavg)

  # Match the length of the climate data (years) to the length of the projections (income covariate data)
  year.avg <- year.avg[ year.avg %in% colnames(inc.array) ]
  temps.avg <- temps.avg[, 1:length(year.avg)][, 1:length(year.avg)]
  prcps.avg <- prcps.avg[, 1:length(year.avg)][, 1:length(year.avg)]


} else {
  stop(paste0('Year indexing is inconsistent between tavg and pavg data. File paths: \n', tavgpath, '\n', pavgpath))
}

# Make sure tmin year indexing is consistent and not longer than projections.
if ( isTRUE(all.equal(year.avg, year.tmin)) ) {
  rm(year.tmin)
} else {
  stop(paste0('Year indexing for tmin is inconsistent or too long.'))
}

if ( isTRUE(all.equal(regions.pavg, regions.tavg)) ) {
  regions <- regions.tavg
  rm(regions.tavg, regions.pavg)
} else {
  stop(paste0('Region indexing is inconsistent between tavg and pavg data. File paths: \n', tavgpath, '\n', pavgpath))
}

# Make sure tmin region indexing is also consistent
if ( isTRUE(all.equal(regions, regions.tmin)) ) {
  rm(regions.tmin)
} else {
  stop(paste0('Region indexing for tmin is inconsistent.'))
}


if (!isTRUE(all.equal(as.character(regions), as.character(rownames(inc.array))))) {
  stop(paste0('Region indexing is inconsistent between climate data and income data. File paths: \n', tavgpath, '\n', incpath))
}



## Set up covariate expected values.
# We use lagged covariates for expectations, so just lag temps.avg and prcps.avg now
tmp <- array(NA, dim=c(dim(temps.avg)[1],1))
temps.avg.lag <- abind(tmp, temps.avg, along=2)
temps.avg.lag <- temps.avg.lag[ , 1:(dim(temps.avg.lag)[2]-1) ]

tmp <- array(NA, dim=c(dim(prcps.avg)[1],1))
prcps.avg.lag <- abind(tmp, prcps.avg, along=2)
prcps.avg.lag <- prcps.avg.lag[ , 1:(dim(prcps.avg.lag)[2]-1) ]

tmp <- array(NA, dim=c(dim(temps.avg)[1],1))
inc.array.lag <- abind(tmp, inc.array, along=2)
inc.array.lag <- inc.array.lag[ , 1:(dim(inc.array.lag)[2]-1) ]

temps.avg <- temps.avg.lag
prcps.avg <- prcps.avg.lag
inc.array <- inc.array.lag
rm(temps.avg.lag, prcps.avg.lag, inc.array.lag)

# We use 2015 values of covariates for all years before 2015.
# For each IR (row), replace the climate covariate value with the 2015 value for
# all years before 2015.
ones.v <- rep(1, dim(prcps.avg[,1:35])[2])
temps.avg[, 1:35] <- temps.avg[, 35] %*% t(ones.v)
prcps.avg[, 1:35] <- prcps.avg[, 35] %*% t(ones.v)
inc.array[, 1:35] <- inc.array[, 35] %*% t(ones.v)

# Impose pbar spline for gdds and kdds and (for rice and wheat) tmin. And pr, will need it later. 
# And assign 2015 values to pre-2015 period.
prcps.avg.gdd.spline <- prcps.avg * (prcps.avg < pbar.kink.gdd) + pbar.kink.gdd * (prcps.avg >= pbar.kink.gdd)
prcps.avg.kdd.spline <- prcps.avg * (prcps.avg < pbar.kink.kdd) + pbar.kink.kdd * (prcps.avg >= pbar.kink.kdd)
prcps.avg.pr.spline <- prcps.avg * (prcps.avg < pbar.kink.pr) + pbar.kink.pr * (prcps.avg >= pbar.kink.pr)

prcps.avg.gdd.spline[, 1:35] <- prcps.avg.gdd.spline[, 35] %*% t(ones.v)
prcps.avg.kdd.spline[, 1:35] <- prcps.avg.kdd.spline[, 35] %*% t(ones.v)
prcps.avg.pr.spline[, 1:35] <- prcps.avg.pr.spline[, 35] %*% t(ones.v)

if ((crop=='rice') | (crop == 'wheat-spring') | (crop == 'wheat-winter')) {
  prcps.avg.tmin.spline <- prcps.avg * (prcps.avg < pbar.kink.tmin) + pbar.kink.tmin * (prcps.avg >= pbar.kink.tmin)
  prcps.avg.tmin.spline[, 1:35] <- prcps.avg.tmin.spline[, 35] %*% t(ones.v)
  
  if (crop == 'wheat-winter') {
    # Winter wheat has a separate pbar-spline for winter season tmin.
    prcps.avg.tmin.spline.wint <- prcps.avg * (prcps.avg < pbar.kink.tmin.wint) + pbar.kink.tmin.wint * (prcps.avg >= pbar.kink.tmin.wint)
    prcps.avg.tmin.spline.wint[, 1:35] <- prcps.avg.tmin.spline.wint[, 35] %*% t(ones.v)
  }
}





##############################################################################################
# Calculate adaptation terms for each region-year. This calculation is memory-intensive in the
# projection system, so for ag we are moving it to this script, for efficiency.
##############################################################################################



# Read in the regression coefficients from the .csvv file and grab three rows:
# The row of predictor names, the row of covariate names, and the row of coefficient values.
coeffs <- read.csv(gammapath, skip=csvv.skip.lines, header=FALSE, stringsAsFactors=FALSE)

if(seed!='unused') {

  print('------------------')
  print(paste0('Randomizing... using numeric seed passed by user for ', crop, ' under model ', model, ' / RCP ', rcp, ' / SSP', ssp, ' / IAM-',iam))
  print(paste0('Value of seed : ', seed))
  print('------------------')

  use_condaenv("base", required=TRUE)
  
  # If <seed> is not '', then this script is being used to replicate a Monte Carlo coefficient draw from the
  # variance covariance matrix. In this case, <seed> must be a numeric value. The Monte Carlos are
  # implemented in python, and so the draw must be replicated in python as well.
  # Note: the last two rows of the csvv give the std. error of the residuals and are not part of the vcv.
  vcv.rows <- 7:(dim(coeffs)[1]-2)
  coeffs.vcv <- as.matrix(coeffs[vcv.rows,])

  # Replicate the Monte Carlo draw (in Python) from the variance covariance matrix.
  # See this git issue: https://gitlab.com/ClimateImpactLab/Impacts/impact-calculations/-/issues/132
  #scipy.stats <- import('scipy.stats')
  np <- import('numpy')
  # pd <- import('pandas')
  
  # Attempt 1 -- this is the original approach in the projection system, but unfortunately is unstable for some VCVs
  # np$random$seed(as.integer(seed))
  # coeffs.draw <- scipy.stats$multivariate_normal$rvs(as.numeric(coeffs[5,]), coeffs.vcv)
  
  # Attempt 2 -- this is a change to the unstable approach above, which fixed some things but not the instability.
  # rng <- np$random$default_rng(as.integer(seed))
  # coeffs.draw <- scipy.stats$multivariate_normal$rvs(as.numeric(coeffs[5,]), coeffs.vcv, random_state=rng)
  
  # Attempt 3 -- this fixes the instability, we believe.
  
  # rng <- np$random$Generator(np$random$PCG64( as.integer(seed) ))  
  ## The above line cannot handle the new 128bit int seeds. See https://gitlab.com/ClimateImpactLab/Impacts/impact-calculations/-/merge_requests/207#note_583977414
  ## py_run_string can handle 128 bit ints though
  py_run_string('import numpy as np')
  py_run_string( paste0('rng = np.random.Generator(np.random.PCG64(',seed,'))') )
  
  coeffs.draw <- py$rng$multivariate_normal(
    mean=as.numeric(coeffs[5,]),
    cov=coeffs.vcv,
    check_valid="raise",
    method='eigh'
  )
  
  coeffs[5,] <- coeffs.draw
  
  # For passing particular MC coeff draws out for diagnostics.
  # print(coeffs.draw)
  # stop()

} else {

  print('------------------')
  print(paste0("Seed parameter was passed the 'unused' string.. Using point estimate response"))
  print('------------------')

}


coeffs <- coeffs [c(1,3,5),]

# Trim whitespace from predictor and covariate names
coeffs[1,] <- trimws(coeffs[1,])
coeffs[2,] <- trimws(coeffs[2,])


get.coeff <- function( clim, cov, csvv.df=coeffs, csvv.vcv=coeffs.vcv, seed=NA ) {
  # Given a .csvv file read in above from gammapath, find the coefficient corresponding to the
  # interaction between <clim> (the weather parameter) and <cov> (the covariate). For main effects
  # of the <clim> parameters, pass a string of '1' as the argument for <cov>.

  return(as.numeric( csvv.df[3, (csvv.df[1,] %in% clim) & (csvv.df[2,] %in% cov)] ))

}



# In every year-ir that is clipped, force the costs to be zero.
# Check for clipping in GDD (clip if GDD coeff < 0) and in KDD (clip if KDD coeff > 0).
# This filter takes a value of 1 when costs should be clipped. Apply it when calculating costs.
no_gdd_clip <- TRUE

if ((crop=='maize') | (crop=='soy') | (crop=='wheat-spring') | (crop=='wheat-winter')) {
  gdd.clip.filter <- ( 0 <
                         get.coeff(gdd_var,'1') +
                         get.coeff(gdd_var,'seasonaltasmax')*temps.avg +
                         get.coeff(gdd_var,'seasonalpr')*prcps.avg.gdd.spline +
                         get.coeff(gdd_var,'seasonaltasmax*seasonalpr')*temps.avg*prcps.avg.gdd.spline +
                         get.coeff(gdd_var,'loggdppc')*inc.array +
                         get.coeff(gdd_var,'ir-share')*irr.array
  )
  
  
  kdd.clip.filter <- ( 0 >
                         get.coeff(kdd_var,'1') +
                         get.coeff(kdd_var,'seasonaltasmax')*temps.avg +
                         get.coeff(kdd_var,'seasonalpr')*prcps.avg.kdd.spline +
                         get.coeff(kdd_var,'seasonaltasmax*seasonalpr')*temps.avg*prcps.avg.kdd.spline +
                         get.coeff(kdd_var,'loggdppc')*inc.array +
                         get.coeff(kdd_var,'ir-share')*irr.array
  )
  
  if (crop=='wheat-winter') {
    # Winter wheat needs fall and winter season gdd/kdd clip filters.
    
    gdd.clip.filter.fall <- ( 0 <
                           get.coeff(gdd_var.fall,'1') +
                           get.coeff(gdd_var.fall,'seasonaltasmax')*temps.avg +
                           get.coeff(gdd_var.fall,'seasonalpr')*prcps.avg.gdd.spline +
                           get.coeff(gdd_var.fall,'seasonaltasmax*seasonalpr')*temps.avg*prcps.avg.gdd.spline +
                           get.coeff(gdd_var.fall,'loggdppc')*inc.array +
                           get.coeff(gdd_var.fall,'ir-share')*irr.array
    )
    
    
    kdd.clip.filter.fall <- ( 0 >
                           get.coeff(kdd_var.fall,'1') +
                           get.coeff(kdd_var.fall,'seasonaltasmax')*temps.avg +
                           get.coeff(kdd_var.fall,'seasonalpr')*prcps.avg.kdd.spline +
                           get.coeff(kdd_var.fall,'seasonaltasmax*seasonalpr')*temps.avg*prcps.avg.kdd.spline +
                           get.coeff(kdd_var.fall,'loggdppc')*inc.array +
                           get.coeff(kdd_var.fall,'ir-share')*irr.array
    )
    
    gdd.clip.filter.wint <- ( 0 <
                                get.coeff(gdd_var.wint,'1') +
                                get.coeff(gdd_var.wint,'seasonaltasmax')*temps.avg +
                                get.coeff(gdd_var.wint,'seasonalpr')*prcps.avg.gdd.spline +
                                get.coeff(gdd_var.wint,'seasonaltasmax*seasonalpr')*temps.avg*prcps.avg.gdd.spline +
                                get.coeff(gdd_var.wint,'loggdppc')*inc.array +
                                get.coeff(gdd_var.wint,'ir-share')*irr.array
    )
    
    
    kdd.clip.filter.wint <- ( 0 >
                                get.coeff(kdd_var.wint,'1') +
                                get.coeff(kdd_var.wint,'seasonaltasmax')*temps.avg +
                                get.coeff(kdd_var.wint,'seasonalpr')*prcps.avg.kdd.spline +
                                get.coeff(kdd_var.wint,'seasonaltasmax*seasonalpr')*temps.avg*prcps.avg.kdd.spline +
                                get.coeff(kdd_var.wint,'loggdppc')*inc.array +
                                get.coeff(kdd_var.wint,'ir-share')*irr.array
    )
    
  }
} else if ((crop=='rice') | crop==('sorghum')) {
  gdd.clip.filter <- ( 0 <
                         get.coeff(gdd_var,'1') +
                         get.coeff(gdd_var,'seasonaltasmax')*temps.avg +
                         get.coeff(gdd_var,'seasonalpr')*prcps.avg.gdd.spline +
                         get.coeff(gdd_var,'loggdppc')*inc.array +
                         get.coeff(gdd_var,'ir-share')*irr.array
  )
  
  
  kdd.clip.filter <- ( 0 >
                         get.coeff(kdd_var,'1') +
                         get.coeff(kdd_var,'seasonaltasmax')*temps.avg +
                         get.coeff(kdd_var,'seasonalpr')*prcps.avg.kdd.spline +
                         get.coeff(kdd_var,'loggdppc')*inc.array +
                         get.coeff(kdd_var,'ir-share')*irr.array
  ) 
} else if (crop=='cassava') {
  gdd.clip.filter <- ( 0 <
                         get.coeff(gdd_var,'1') +
                         get.coeff(gdd_var,'seasonaltasmax')*temps.avg +
                         get.coeff(gdd_var,'seasonalpr')*prcps.avg.gdd.spline +
                         get.coeff(gdd_var,'loggdppc')*inc.array
  )
  
  
  kdd.clip.filter <- ( 0 >
                         get.coeff(kdd_var,'1') +
                         get.coeff(kdd_var,'seasonaltasmax')*temps.avg +
                         get.coeff(kdd_var,'seasonalpr')*prcps.avg.kdd.spline +
                         get.coeff(kdd_var,'loggdppc')*inc.array
  ) 
} else {
  print('This crop is not yet configured.')
  stop()
}



if(no_gdd_clip) {
  gdd.clip.filter <- gdd.clip.filter*0 + 1
  # Set NA values
  gdd.clip.filter[is.na(gdd.clip.filter)] <- 1
  kdd.clip.filter[is.na(kdd.clip.filter)] <- 0
  
  if(crop=='wheat-winter') {
    gdd.clip.filter.fall <- gdd.clip.filter.fall*0 + 1
    gdd.clip.filter.wint <- gdd.clip.filter.wint*0 + 1
    # Set NA values
    gdd.clip.filter.fall[is.na(gdd.clip.filter.fall)] <- 1
    kdd.clip.filter.fall[is.na(kdd.clip.filter.fall)] <- 0
    gdd.clip.filter.wint[is.na(gdd.clip.filter.wint)] <- 1
    kdd.clip.filter.wint[is.na(kdd.clip.filter.wint)] <- 0
  }
  

} else {
  # Set NA values to zero
  gdd.clip.filter[is.na(gdd.clip.filter)] <- 0
  kdd.clip.filter[is.na(kdd.clip.filter)] <- 0
  
  if(crop=='wheat-winter') {
    gdd.clip.filter.fall[is.na(gdd.clip.filter.fall)] <- 0
    kdd.clip.filter.fall[is.na(kdd.clip.filter.fall)] <- 0
    gdd.clip.filter.wint[is.na(gdd.clip.filter.wint)] <- 0
    kdd.clip.filter.wint[is.na(kdd.clip.filter.wint)] <- 0
  }
  
}



#print('Precip data dimensions are:')
#print(dim(pr.yr))



### Compute marginals terms
# Maize, soy, and both wheats have Tbar x Pbar covariate interactions
# Rice, cassava, and sorghum do not

# Winter wheat marginals terms are structured differently, due to separate structure of the weather data. Remember, winter wheat
# weather data has a season identifier appended for fall and winter, but not summer (so that one season's names -- summer -- are 
# similar to other crops).  E.g. dd.yr is summer degree days, while dd.yr.fall is fall, and dd.yr.wint is winter.

# For use of `if`() as a ternary operator which can take scalar input and give matrix output, see https://stackoverflow.com/a/48890803

# Initialize a zeros matrix matching the dimensions of the data, for adding zeros when interaction terms are not present for a crop.
zeros.mat <- dd.yr[1,,] * 0


## d(y_gdd)/d(Tbar) + d(y_kdd)/d(Tbar)

marginal.tbar.temp <- ( dd.yr[1,,] * gdd.clip.filter *
                        ( get.coeff(gdd_var,'seasonaltasmax') + `if`(has.TxP,
                                                                     get.coeff(gdd_var,'seasonaltasmax*seasonalpr')*prcps.avg.gdd.spline, zeros.mat) ) +
                        dd.yr[2,,] * kdd.clip.filter *
                        ( get.coeff(kdd_var,'seasonaltasmax') + `if`(has.TxP,
                                                                     get.coeff(kdd_var,'seasonaltasmax*seasonalpr')*prcps.avg.kdd.spline, zeros.mat) )
)

# Break into gdd and kdd components (for winter wheat, these are the summer season components, so denote them that way)
marginal.tbar.gdd.summ <- ( dd.yr[1,,] * gdd.clip.filter *
                          ( get.coeff(gdd_var,'seasonaltasmax') + `if`(has.TxP,
                                                                       get.coeff(gdd_var,'seasonaltasmax*seasonalpr')*prcps.avg.gdd.spline, zeros.mat) ) 
)

marginal.tbar.kdd.summ <- ( dd.yr[2,,] * kdd.clip.filter *
                          ( get.coeff(kdd_var,'seasonaltasmax') + `if`(has.TxP,
                                                                       get.coeff(kdd_var,'seasonaltasmax*seasonalpr')*prcps.avg.kdd.spline, zeros.mat) )
)



if (crop == 'wheat-winter') {
  # Add marginals terms for the fall and winter seasons.
  marginal.tbar.temp <- marginal.tbar.temp +
                        # Fall
                        ( dd.yr.fall[1,,] * gdd.clip.filter.fall *
                            ( get.coeff(gdd_var.fall,'seasonaltasmax') + `if`(has.TxP,
                                                                         get.coeff(gdd_var.fall,'seasonaltasmax*seasonalpr')*prcps.avg.gdd.spline, zeros.mat) ) +
                            dd.yr.fall[2,,] * kdd.clip.filter.fall *
                            ( get.coeff(kdd_var.fall,'seasonaltasmax') + `if`(has.TxP,
                                                                         get.coeff(kdd_var.fall,'seasonaltasmax*seasonalpr')*prcps.avg.kdd.spline, zeros.mat) ) 
  ) +
                        # Winter
                        ( dd.yr.wint[1,,] * gdd.clip.filter.wint *
                            ( get.coeff(gdd_var.wint,'seasonaltasmax') + `if`(has.TxP,
                                                                              get.coeff(gdd_var.wint,'seasonaltasmax*seasonalpr')*prcps.avg.gdd.spline, zeros.mat) ) +
                            dd.yr.wint[2,,] * kdd.clip.filter.wint *
                            ( get.coeff(kdd_var.wint,'seasonaltasmax') + `if`(has.TxP,
                                                                              get.coeff(kdd_var.wint,'seasonaltasmax*seasonalpr')*prcps.avg.kdd.spline, zeros.mat) )  
  )
  
  # Break into gdd and kdd components by fall/winter season
  marginal.tbar.gdd.fall <- ( dd.yr.fall[1,,] * gdd.clip.filter.fall *
        ( get.coeff(gdd_var.fall,'seasonaltasmax') + `if`(has.TxP,
                                                          get.coeff(gdd_var.fall,'seasonaltasmax*seasonalpr')*prcps.avg.gdd.spline, zeros.mat) ) 
        )
  
  marginal.tbar.kdd.fall <- ( dd.yr.fall[2,,] * kdd.clip.filter.fall *
        ( get.coeff(kdd_var.fall,'seasonaltasmax') + `if`(has.TxP,
                                                          get.coeff(kdd_var.fall,'seasonaltasmax*seasonalpr')*prcps.avg.kdd.spline, zeros.mat) ) 
    ) 
  
  marginal.tbar.gdd.wint <- ( dd.yr.wint[1,,] * gdd.clip.filter.wint *
        ( get.coeff(gdd_var.wint,'seasonaltasmax') + `if`(has.TxP,
                                                          get.coeff(gdd_var.wint,'seasonaltasmax*seasonalpr')*prcps.avg.gdd.spline, zeros.mat) )  
    )
  
  marginal.tbar.kdd.wint <- ( dd.yr.wint[2,,] * kdd.clip.filter.wint *
        ( get.coeff(kdd_var.wint,'seasonaltasmax') + `if`(has.TxP,
                                                          get.coeff(kdd_var.wint,'seasonaltasmax*seasonalpr')*prcps.avg.kdd.spline, zeros.mat) )  
    )
  
}


# print('diagnostics')
# print(dim(dd.yr))
# print(dim(gdd.clip.filter))
# print(dim(kdd.clip.filter))
# print(dim(prcps.avg.gdd.spline))
# print(get.coeff(gdd_var,'seasonaltasmax'))
# print(dim(marginal.tbar.temp))
# print(get.coeff(pr_var.bin1,'seasonaltasmax'))

## d(y_pr)/d(Tbar)

if ((crop != 'cassava') & (crop != 'wheat-spring') & (crop != 'wheat-winter')) {
  # Cassava and spring wheat do not have different prcp responses over the growing season. Winter wheat data is structured differently. 
  # All other crops do have different prcp responses, where the precip response differs by "month-bins" (groupings of months).
  
  # Maize month-bins are months 1, 2-4, 5+
  marginal.tbar.prcp <- (
    # Month-bin 1 (for maize, this is month 1)
    pr.yr[1,,] *
      ( get.coeff(pr_var.bin1,'seasonaltasmax') + `if`(has.TxP,
                                                       get.coeff(pr_var.bin1,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) ) +
      pr.yr[2,,] *
      ( get.coeff(pr2_var.bin1,'seasonaltasmax') + `if`(has.TxP,
                                                        get.coeff(pr2_var.bin1,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) ) +
      
      # Month-bin 2 (for maize, this is months 2-4)
      pr.yr[3,,] *
      ( get.coeff(pr_var.bin2,'seasonaltasmax') + `if`(has.TxP,
                                                       get.coeff(pr_var.bin2,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) ) +
      pr.yr[4,,] *
      ( get.coeff(pr2_var.bin2,'seasonaltasmax') + `if`(has.TxP,
                                                        get.coeff(pr2_var.bin2,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) ) +
      
      # Month-bin 3 (for maize, this is months 5+)
      pr.yr[5,,] *
      ( get.coeff(pr_var.bin3,'seasonaltasmax') + `if`(has.TxP,
                                                       get.coeff(pr_var.bin3,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) ) +
      pr.yr[6,,] *
      ( get.coeff(pr2_var.bin3,'seasonaltasmax') + `if`(has.TxP,
                                                        get.coeff(pr2_var.bin3,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
  )
  
  if( (crop=='soy') ) {
    
    # Soy has four month-bins, not three
    marginal.tbar.prcp <- marginal.tbar.prcp +
      pr.yr[7,,] *
      ( get.coeff(pr_var.bin4,'seasonaltasmax') + `if`(has.TxP,
                                                       get.coeff(pr_var.bin4,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) ) +
      pr.yr[8,,] *
      ( get.coeff(pr2_var.bin4,'seasonaltasmax') + `if`(has.TxP,
                                                        get.coeff(pr2_var.bin4,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
    
  }

} else {

  # Cassava and spring wheat, and winter wheat summer season
  marginal.tbar.prcp <- ( pr.yr[1,,] * ( get.coeff(pr_var.bin1,'seasonaltasmax') + 
                                         `if`(has.TxP, get.coeff(pr_var.bin1,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
    ) +
    ( pr.yr[2,,] * ( get.coeff(pr2_var.bin1,'seasonaltasmax') + 
                       `if`(has.TxP, get.coeff(pr2_var.bin1,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
    )
  
 
  if ((crop == 'wheat-spring') | (crop == 'wheat-winter')) {
    # Spring and winter wheat have 4th order prcp polynomials, so two more terms than the quadratic for cassava.
    marginal.tbar.prcp <- marginal.tbar.prcp +
      ( pr.yr[3,,] * ( get.coeff(pr3_var.bin1,'seasonaltasmax') + 
                         `if`(has.TxP, get.coeff(pr3_var.bin1,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr[4,,] * ( get.coeff(pr4_var.bin1,'seasonaltasmax') + 
                         `if`(has.TxP, get.coeff(pr4_var.bin1,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      )
  }
  
  if (crop == 'wheat-winter') {
    # Fall and winter for winter wheat
    
    # Break out (save) the summer prcp marginals
    marginal.tbar.prcp.summ <- marginal.tbar.prcp
    
    # Now go ahead and add in fall and winter marginals, they will be separately broken out below.
    marginal.tbar.prcp <- marginal.tbar.prcp +
    
      # Fall
      ( pr.yr.fall[1,,] * ( get.coeff(pr_var.bin1.fall,'seasonaltasmax') + 
                                             `if`(has.TxP, get.coeff(pr_var.bin1.fall,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.fall[2,,] * ( get.coeff(pr2_var.bin1.fall,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr2_var.bin1.fall,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.fall[3,,] * ( get.coeff(pr3_var.bin1.fall,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr3_var.bin1.fall,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.fall[4,,] * ( get.coeff(pr4_var.bin1.fall,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr4_var.bin1.fall,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      
      # Winter
      ( pr.yr.wint[1,,] * ( get.coeff(pr_var.bin1.wint,'seasonaltasmax') + 
                         `if`(has.TxP, get.coeff(pr_var.bin1.wint,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.wint[2,,] * ( get.coeff(pr2_var.bin1.wint,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr2_var.bin1.wint,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.wint[3,,] * ( get.coeff(pr3_var.bin1.wint,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr3_var.bin1.wint,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.wint[4,,] * ( get.coeff(pr4_var.bin1.wint,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr4_var.bin1.wint,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      )
    
    # Break out prcp marginals by season (fall/winter)
    marginal.tbar.prcp.fall <- ( pr.yr.fall[1,,] * ( get.coeff(pr_var.bin1.fall,'seasonaltasmax') + 
                                                       `if`(has.TxP, get.coeff(pr_var.bin1.fall,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
    ) +
      ( pr.yr.fall[2,,] * ( get.coeff(pr2_var.bin1.fall,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr2_var.bin1.fall,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.fall[3,,] * ( get.coeff(pr3_var.bin1.fall,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr3_var.bin1.fall,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.fall[4,,] * ( get.coeff(pr4_var.bin1.fall,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr4_var.bin1.fall,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      )
    
    marginal.tbar.prcp.wint <- ( pr.yr.wint[1,,] * ( get.coeff(pr_var.bin1.wint,'seasonaltasmax') + 
                                                       `if`(has.TxP, get.coeff(pr_var.bin1.wint,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
    ) +
      ( pr.yr.wint[2,,] * ( get.coeff(pr2_var.bin1.wint,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr2_var.bin1.wint,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.wint[3,,] * ( get.coeff(pr3_var.bin1.wint,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr3_var.bin1.wint,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      ) +
      ( pr.yr.wint[4,,] * ( get.coeff(pr4_var.bin1.wint,'seasonaltasmax') + 
                              `if`(has.TxP, get.coeff(pr4_var.bin1.wint,'seasonaltasmax*seasonalpr')*prcps.avg.pr.spline, zeros.mat) )
      )
    
  }
  
}



## d(y_gdd)/d(Pbar) + d(y_kdd)/d(Pbar)

marginal.pbar.temp <- ( dd.yr[1,,] * gdd.clip.filter *
                        ( get.coeff(gdd_var,'seasonalpr') + `if`(has.TxP, 
                                                                 get.coeff(gdd_var,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.gdd) +
                        dd.yr[2,,] * kdd.clip.filter *
                        ( get.coeff(kdd_var,'seasonalpr') + `if`(has.TxP, 
                                                                 get.coeff(kdd_var,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.kdd)
)

# Break into gdd and kdd components (for winter wheat, these are the summer season components, so denote them that way)
marginal.pbar.gdd.summ <- ( dd.yr[1,,] * gdd.clip.filter *
                              ( get.coeff(gdd_var,'seasonalpr') + `if`(has.TxP, 
                                                                       get.coeff(gdd_var,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.gdd) 
)

marginal.pbar.kdd.summ <- ( dd.yr[2,,] * kdd.clip.filter *
                              ( get.coeff(kdd_var,'seasonalpr') + `if`(has.TxP, 
                                                                       get.coeff(kdd_var,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.kdd)
)


if (crop == 'wheat-winter') {
  # Fall and winter for winter wheat
  marginal.pbar.temp <- marginal.pbar.temp +
                        # Fall
                        ( dd.yr.fall[1,,] * gdd.clip.filter.fall *
                            ( get.coeff(gdd_var.fall,'seasonalpr') + `if`(has.TxP, 
                                                                     get.coeff(gdd_var.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.gdd) +
                            dd.yr.fall[2,,] * kdd.clip.filter.fall *
                            ( get.coeff(kdd_var.fall,'seasonalpr') + `if`(has.TxP, 
                                                                     get.coeff(kdd_var.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.kdd)
                        ) +
                        # Winter
                        ( dd.yr.wint[1,,] * gdd.clip.filter.wint *
                            ( get.coeff(gdd_var.wint,'seasonalpr') + `if`(has.TxP, 
                                                                          get.coeff(gdd_var.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.gdd) +
                            dd.yr.wint[2,,] * kdd.clip.filter.wint *
                            ( get.coeff(kdd_var.wint,'seasonalpr') + `if`(has.TxP, 
                                                                          get.coeff(kdd_var.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.kdd)
                        )
  
  # Break out gdd/kdd components by fall/winter season
  marginal.pbar.gdd.fall <- ( dd.yr.fall[1,,] * gdd.clip.filter.fall *
                                ( get.coeff(gdd_var.fall,'seasonalpr') + `if`(has.TxP, 
                                                                              get.coeff(gdd_var.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.gdd)
  )
  
  marginal.pbar.kdd.fall <- ( dd.yr.fall[2,,] * kdd.clip.filter.fall *
                                ( get.coeff(kdd_var.fall,'seasonalpr') + `if`(has.TxP, 
                                                                              get.coeff(kdd_var.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.kdd)
  )
  
  marginal.pbar.gdd.wint <- ( dd.yr.wint[1,,] * gdd.clip.filter.wint *
                                ( get.coeff(gdd_var.wint,'seasonalpr') + `if`(has.TxP, 
                                                                              get.coeff(gdd_var.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.gdd)
  )
  
  marginal.pbar.kdd.wint <- ( dd.yr.wint[2,,] * kdd.clip.filter.wint *
                                ( get.coeff(kdd_var.wint,'seasonalpr') + `if`(has.TxP, 
                                                                              get.coeff(kdd_var.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.kdd)
  )
    
}

## d(y_pr)/d(Pbar)

if ((crop != 'cassava') & (crop != 'wheat-spring') & (crop != 'wheat-winter')) {
  # Cassava and spring wheat do not have different prcp responses over the growing season. Winter wheat data is structured differently.
  # All other crops do have different prcp responses, where the precip response differs by "month-bins" (groupings of months).
  marginal.pbar.prcp <- (
                          # Month 1
                          pr.yr[1,,] *
                          ( get.coeff(pr_var.bin1,'seasonalpr') + `if`(has.TxP,
                                                                       get.coeff(pr_var.bin1,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                          pr.yr[2,,] *
                          ( get.coeff(pr2_var.bin1,'seasonalpr') + `if`(has.TxP,
                                                                        get.coeff(pr2_var.bin1,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
  
                          # Months 2-4
                          pr.yr[3,,] *
                          ( get.coeff(pr_var.bin2,'seasonalpr') + `if`(has.TxP,
                                                                       get.coeff(pr_var.bin2,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                          pr.yr[4,,] *
                          ( get.coeff(pr2_var.bin2,'seasonalpr') + `if`(has.TxP,
                                                                        get.coeff(pr2_var.bin2,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
  
                          # Months 5+
                          pr.yr[5,,] *
                          ( get.coeff(pr_var.bin3,'seasonalpr') + `if`(has.TxP,
                                                                       get.coeff(pr_var.bin3,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                          pr.yr[6,,] *
                          ( get.coeff(pr2_var.bin3,'seasonalpr') + `if`(has.TxP,
                                                                        get.coeff(pr2_var.bin3,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) )
  ) * (prcps.avg<pbar.kink.pr)
  
  if(crop=='soy') {
  
    marginal.pbar.prcp <- marginal.pbar.prcp +
                          (
                          pr.yr[7,,] *
                          ( get.coeff(pr_var.bin4,'seasonalpr') + `if`(has.TxP,
                                                                       get.coeff(pr_var.bin4,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                          pr.yr[8,,] *
                          ( get.coeff(pr2_var.bin4,'seasonalpr') + `if`(has.TxP,
                                                                        get.coeff(pr2_var.bin4,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) )
    ) * (prcps.avg<pbar.kink.pr)
  
  }
} else {
  
  # Cassava and spring wheat and, winter wheat summer season
  marginal.pbar.prcp <- ( pr.yr[1,,] * ( get.coeff(pr_var.bin1,'seasonalpr') + 
                                         `if`(has.TxP, get.coeff(pr_var.bin1,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                          pr.yr[2,,] * ( get.coeff(pr2_var.bin1,'seasonalpr') + 
                                          `if`(has.TxP, get.coeff(pr2_var.bin1,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) )
  ) * (prcps.avg<pbar.kink.pr)
  
  # Spring and winter wheat are 4th order prcp polynomials, add those terms (winter wheat summer season).
  if ((crop == 'wheat-spring') | (crop == 'wheat-winter')) {
    marginal.pbar.prcp <- marginal.pbar.prcp +
      ( pr.yr[3,,] * ( get.coeff(pr3_var.bin1,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr3_var.bin1,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
        pr.yr[4,,] * ( get.coeff(pr4_var.bin1,'seasonalpr') + 
                           `if`(has.TxP, get.coeff(pr4_var.bin1,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) )
      ) * (prcps.avg<pbar.kink.pr)
  }
    
  
  if (crop == 'wheat-winter') {
    # Fall and winter for winter wheat
    
    # First save the summer marginals (fall and winter will be broken out below.)
    marginal.pbar.prcp.summ <- marginal.pbar.prcp
    
    # Now go ahead and add in fall and winter marginals, they will be separately broken out below.
    marginal.pbar.prcp <- marginal.pbar.prcp +
      
      # Fall
      ( pr.yr.fall[1,,] * ( get.coeff(pr_var.bin1.fall,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr_var.bin1.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
        pr.yr.fall[2,,] * ( get.coeff(pr2_var.bin1.fall,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr2_var.bin1.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
        pr.yr.fall[3,,] * ( get.coeff(pr3_var.bin1.fall,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr3_var.bin1.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
        pr.yr.fall[4,,] * ( get.coeff(pr4_var.bin1.fall,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr4_var.bin1.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) )
      ) * (prcps.avg<pbar.kink.pr) +
      
      # Winter
      ( pr.yr.wint[1,,] * ( get.coeff(pr_var.bin1.wint,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr_var.bin1.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
        pr.yr.wint[2,,] * ( get.coeff(pr2_var.bin1.wint,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr2_var.bin1.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
        pr.yr.wint[3,,] * ( get.coeff(pr3_var.bin1.wint,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr3_var.bin1.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
        pr.yr.wint[4,,] * ( get.coeff(pr4_var.bin1.wint,'seasonalpr') + 
                         `if`(has.TxP, get.coeff(pr4_var.bin1.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) 
      ) * (prcps.avg<pbar.kink.pr)
      
      # Now break out the fall and winter marginals
      marginal.pbar.prcp.fall <- ( pr.yr.fall[1,,] * ( get.coeff(pr_var.bin1.fall,'seasonalpr') + 
                                                     `if`(has.TxP, get.coeff(pr_var.bin1.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                                 pr.yr.fall[2,,] * ( get.coeff(pr2_var.bin1.fall,'seasonalpr') + 
                                                       `if`(has.TxP, get.coeff(pr2_var.bin1.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                                 pr.yr.fall[3,,] * ( get.coeff(pr3_var.bin1.fall,'seasonalpr') + 
                                                       `if`(has.TxP, get.coeff(pr3_var.bin1.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                                 pr.yr.fall[4,,] * ( get.coeff(pr4_var.bin1.fall,'seasonalpr') + 
                                                       `if`(has.TxP, get.coeff(pr4_var.bin1.fall,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) )
  ) * (prcps.avg<pbar.kink.pr)
      
      marginal.pbar.prcp.wint <- ( pr.yr.wint[1,,] * ( get.coeff(pr_var.bin1.wint,'seasonalpr') + 
                                                     `if`(has.TxP, get.coeff(pr_var.bin1.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                                 pr.yr.wint[2,,] * ( get.coeff(pr2_var.bin1.wint,'seasonalpr') + 
                                                       `if`(has.TxP, get.coeff(pr2_var.bin1.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                                 pr.yr.wint[3,,] * ( get.coeff(pr3_var.bin1.wint,'seasonalpr') + 
                                                       `if`(has.TxP, get.coeff(pr3_var.bin1.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) +
                                 pr.yr.wint[4,,] * ( get.coeff(pr4_var.bin1.wint,'seasonalpr') + 
                                                       `if`(has.TxP, get.coeff(pr4_var.bin1.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) 
  ) * (prcps.avg<pbar.kink.pr)

    }
    
}


## d(y_tmin)/d(Tbar) & d(y_tmin)/d(Pbar)
# Only for rice and wheat, set to zero otherwise.

if ((crop == 'rice') | (crop == 'wheat-spring') | (crop == 'wheat-winter')) {

  marginal.tbar.tmin <- ( tmin.yr  *
                          ( get.coeff(tmin_var,'seasonaltasmax') + `if`(has.TxP,
                                                                        get.coeff(tmin_var,'seasonaltasmax*seasonalpr')*prcps.avg.tmin.spline, zeros.mat) )
                        )

  marginal.pbar.tmin <- ( tmin.yr *
                            ( get.coeff(tmin_var,'seasonalpr') + `if`(has.TxP,
                                                                      get.coeff(tmin_var,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.tmin)
                        )
  
  # Save the summer marginals for winter wheat analysis
  marginal.tbar.tmin.summ <- marginal.tbar.tmin
  marginal.pbar.tmin.summ <- marginal.pbar.tmin
  
  if (crop == 'wheat-winter'){ 
    # Winter season tmin components for winter wheat
    
    marginal.tbar.tmin <- marginal.tbar.tmin + 
                          ( tmin.yr.wint  *
                              ( get.coeff(tmin_var.wint,'seasonaltasmax') + `if`(has.TxP,
                                                                            get.coeff(tmin_var.wint,'seasonaltasmax*seasonalpr')*prcps.avg.tmin.spline.wint, zeros.mat) )
    )
    
    marginal.pbar.tmin <- marginal.pbar.tmin + 
                          ( tmin.yr.wint *
                              ( get.coeff(tmin_var.wint,'seasonalpr') + `if`(has.TxP,
                                                                        get.coeff(tmin_var.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.tmin.wint)
    )
    
    # Break out the winter tmin marginals separately for winter wheat analysis
    marginal.tbar.tmin.wint <- ( tmin.yr.wint  *
          ( get.coeff(tmin_var.wint,'seasonaltasmax') + `if`(has.TxP,
                                                             get.coeff(tmin_var.wint,'seasonaltasmax*seasonalpr')*prcps.avg.tmin.spline.wint, zeros.mat) )
      )
    
    marginal.pbar.tmin.wint <- ( tmin.yr.wint *
                                   ( get.coeff(tmin_var.wint,'seasonalpr') + `if`(has.TxP,
                                                                                  get.coeff(tmin_var.wint,'seasonaltasmax*seasonalpr')*temps.avg, zeros.mat) ) * (prcps.avg<pbar.kink.tmin.wint)
    )
    
  }

  # Diagnostics
  if (1==0) {
    print('##### COSTS DIAGNOSTICS ####')
    print('Dim, marginal.tbar.tmin, marginal.pbar.tmin, dim(marginal.tbar.temp), marginal.tbar.temp')
    print(dim(marginal.tbar.tmin))
    print(marginal.tbar.tmin[1:5,1:5])
    print(marginal.pbar.tmin[1:5,1:5])
    print(dim(marginal.tbar.temp))
    print(marginal.tbar.temp[1:5,1:5])
    print(class(marginal.tbar.temp))
    print(class(marginal.tbar.tmin))
    print(class(marginal.pbar.tmin))
    
    yr.idx <- 108:112
        
    my.ir <- 'IND.31.483.1960'
    my.idx <- which(regions==my.ir)
    # print(regions[my.idx])
    print('##########')
    print(paste0('Diagnostics for region ', my.ir))
    print(year.avg[yr.idx])
    print('marginal.tbar.(temp,prcp,tmin), margina.pbar.(temp.prcp,tmin)')
    print('##########')
    print(marginal.tbar.temp[my.idx,yr.idx])
    print(marginal.tbar.prcp[my.idx,yr.idx])
    print(marginal.tbar.tmin[my.idx,yr.idx])
    print(marginal.pbar.temp[my.idx,yr.idx])
    print(marginal.pbar.prcp[my.idx,yr.idx])
    print(marginal.pbar.tmin[my.idx,yr.idx])
    print('##########')
    print('##########')
    my.ir <- 'IND.31.477.1929' # 'IND.31.483.1960'
    my.idx <- which(regions==my.ir)
    print(my.idx)
    print(paste0('Diagnostics for region ', my.ir))
    print(year.avg[yr.idx])
    print('marginal.tbar.(temp,prcp,tmin), margina.pbar.(temp.prcp,tmin)')
    print('##########')
    print(marginal.tbar.temp[my.idx,yr.idx])
    print(marginal.tbar.prcp[my.idx,yr.idx])
    print(marginal.tbar.tmin[my.idx,yr.idx])
    print(marginal.pbar.temp[my.idx,yr.idx])
    print(marginal.pbar.prcp[my.idx,yr.idx])
    print(marginal.pbar.tmin[my.idx,yr.idx])
    
    print('weather data: tmin, tmin_winter, gdd_winter, kdd_winter')
    print(tmin.yr[my.idx,yr.idx])
    print(tmin.yr.wint[my.idx,yr.idx])
    print(dd.yr.wint[1,my.idx,yr.idx])
    print(dd.yr.wint[2,my.idx,yr.idx])
    
    print('##')
    print('Specific Winter GDD / Tbar diagnostics')
    print('##')
    
    print(dd.yr.wint[1,my.idx,yr.idx])
    print(gdd.clip.filter.wint[my.idx,yr.idx])
    print(get.coeff(gdd_var.wint,'seasonaltasmax'))
    print(get.coeff(gdd_var.wint,'seasonaltasmax*seasonalpr'))
    print(prcps.avg.gdd.spline[my.idx,yr.idx])
    print(prcps.avg[my.idx,yr.idx])
    print(temps.avg[my.idx,yr.idx])
    

    tmp <- dd.yr.wint[1,,] * gdd.clip.filter.wint *
      ( get.coeff(gdd_var.wint,'seasonaltasmax') + `if`(has.TxP,
                                                        get.coeff(gdd_var.wint,'seasonaltasmax*seasonalpr')*prcps.avg.gdd.spline, zeros.mat) )

    print(tmp[my.idx,yr.idx])
    
    
    
    # print('Some nearby regions')
    # print(regions[3196:3200])
    # print(dd.yr.wint[1,3196:3200,yr.idx])
    # print(dd.yr.wint[1,3196:3200,1:5])
    # print('#')
    # print(dd.yr.wint[1,3196:3200,])
    # print('#')
    # print(dd.yr.wint[2,3196:3200,])
    # print('#')
    # 
    # print('some random regions')
    # print(regions[1196:1200])
    # print('#')
    # print(dd.yr.wint[1,1196:1200,])
    # print('#')
    # 
    # print('some more random regions')
    # print(regions[196:200])
    # print('#')
    # print(dd.yr.wint[1,196:200,])
    # print('#')
    # 
    # print('some additional random regions')
    # print(regions[10196:10200])
    # print('#')
    # print(dd.yr.wint[1,10196:10200,])
    # print('#')
    # 
    # print('Some Canadian Regins')
    # print(regions[1:10])
    # print(year.avg[60:69])
    # print(dd.yr.wint[1,1:10,70:79])
    # print('##########')
    
    
    
  }


} else {
  marginal.tbar.tmin <- zeros.mat # marginal.tbar.temp * 0
  marginal.pbar.tmin <- zeros.mat # marginal.tbar.temp * 0
}

if (crop != 'wheat-winter') {
  # zero out all the new marginals by season that just apply to winter wheat analysis
  # just to keep things from breaking for non-winter-wheat crops
  marginal.tbar.gdd.fall <- zeros.mat
  marginal.tbar.kdd.fall <- zeros.mat
  marginal.tbar.gdd.wint <- zeros.mat
  marginal.tbar.kdd.wint <- zeros.mat
  marginal.pbar.gdd.fall <- zeros.mat
  marginal.pbar.kdd.fall <- zeros.mat
  marginal.pbar.gdd.wint <- zeros.mat
  marginal.pbar.kdd.wint <- zeros.mat
  marginal.tbar.prcp.fall <- zeros.mat
  marginal.tbar.prcp.wint <- zeros.mat
  marginal.pbar.prcp.fall <- zeros.mat
  marginal.pbar.prcp.wint <- zeros.mat
  marginal.tbar.tmin.wint <- zeros.mat
  marginal.pbar.tmin.wint <- zeros.mat
  marginal.tbar.tmin.summ <- zeros.mat
  marginal.pbar.tmin.summ <- zeros.mat
}


## dy/dTbar & dy/dPbar

marginal.tbar <- marginal.tbar.temp + marginal.tbar.prcp + marginal.tbar.tmin
marginal.pbar <- marginal.pbar.temp + marginal.pbar.prcp + marginal.pbar.tmin

## Weather-by-season marginals, for winter wheat diagnostics
# Others already done, just sum gdd/kdd marginals for an aggregate dd marginal
# marginal.tbar.temp.summ <- marginal.tbar.gdd.summ + marginal.tbar.kdd.summ
# marginal.tbar.temp.fall <- marginal.tbar.gdd.fall + marginal.tbar.kdd.fall
# marginal.tbar.temp.wint <- marginal.tbar.gdd.wint + marginal.tbar.kdd.wint
# marginal.pbar.temp.summ <- marginal.pbar.gdd.summ + marginal.pbar.kdd.summ
# marginal.pbar.temp.fall <- marginal.pbar.gdd.fall + marginal.pbar.kdd.fall
# marginal.pbar.temp.wint <- marginal.pbar.gdd.wint + marginal.pbar.kdd.wint



if(1==0){
  # print(marginal.tbar[1000:1005,56:60])
  # print(marginal.pbar[1000:1005,56:60])
  # print(marginal.pbar.temp[1000:1005,56:60])
  # print(marginal.pbar.prcp[1000:1005,56:60])

  # print(pr.yr[1,1000:1005,56:60])
  # print(pr.yr[2,1000:1005,56:60])
  # print(pr.yr[3,1000:1005,56:60])
  # print(pr.yr[4,1000:1005,56:60])
  # print(pr.yr[5,1000:1005,56:60])
  # print(pr.yr[6,1000:1005,56:60])

  print('Tbar data:')
  print(temps.avg[1000:1005,56:60])
  # print(paste0('pr-Pbar coeff: ', get.coeff(pr_var.bin1,'seasonalpr'), '; pr-Tbar-Pbar coeff: ', get.coeff(pr_var.bin1,'seasonaltasmax*seasonalpr') ))
  print('Pbar data:')
  print(prcps.avg[1000:1005,56:60])
}


###### stop()


### These marginals need to be lagged, and then averaged over a 15-year Bartlett.
## See discussion here: https://gitlab.com/ClimateImpactLab/Impacts/impact-calculations/-/issues/80#note_318728229
lag.and.moving.average <- function( data.mx, avg.period=15 ) {
  # A function to lag a 2-dimentional matrix of impact regions by years, then
  # compute the moving average (Bartlett kernal).
  # data.mx should be a matrix.

  tmp <- array(NA, dim=c(dim(data.mx)[1],1))
  data.mx.lag <- abind(tmp, data.mx, along=2)
  data.mx.lag <- data.mx.lag[ , 1:(dim(data.mx.lag)[2]-1) ]
  colnames(data.mx.lag) <- colnames(data.mx)

  for (r in 1:dim(data.mx.lag)[1]) {
    # Make sure there are at least some non-missing and non-inf values
    if (sum(is.finite(data.mx.lag[r,])) > 0) {
      data.mx.lag[r,] <- movavg(data.mx.lag[r,], avg.period, 'w')
    }
  }
  data.mx.lag
}

# Note: see comment on line 1292 and following below. These were "marginal.[XXX].lag" rather than ".avg" terms
marginal.tbar.avg <- lag.and.moving.average( marginal.tbar, avg.period=15 )
marginal.pbar.avg <- lag.and.moving.average( marginal.pbar, avg.period=15 )
#### component costs
marginal.tbar.temp.avg <- lag.and.moving.average( marginal.tbar.temp, avg.period=15 )
marginal.pbar.temp.avg <- lag.and.moving.average( marginal.pbar.temp, avg.period=15 )
                 
marginal.tbar.tmin.avg <- lag.and.moving.average( marginal.tbar.tmin, avg.period=15 )
marginal.pbar.tmin.avg <- lag.and.moving.average( marginal.pbar.tmin, avg.period=15 )
                 
marginal.tbar.prcp.avg <- lag.and.moving.average( marginal.tbar.prcp, avg.period=15 )
marginal.pbar.prcp.avg <- lag.and.moving.average( marginal.pbar.prcp, avg.period=15 )

# new add: winter wheat specific terms
# marginal.tbar.temp.summ.avg <- lag.and.moving.average( marginal.tbar.temp.summ, avg.period=15 )
# marginal.tbar.temp.fall.avg <- lag.and.moving.average( marginal.tbar.temp.fall, avg.period=15 )
# marginal.tbar.temp.wint.avg <- lag.and.moving.average( marginal.tbar.temp.wint, avg.period=15 )

# marginal.pbar.temp.summ.avg <- lag.and.moving.average( marginal.pbar.temp.summ, avg.period=15 )
# marginal.pbar.temp.fall.avg <- lag.and.moving.average( marginal.pbar.temp.fall, avg.period=15 )
# marginal.pbar.temp.wint.avg <- lag.and.moving.average( marginal.pbar.temp.wint, avg.period=15 )

# marginal.tbar.prcp.summ.avg <- lag.and.moving.average( marginal.tbar.prcp.summ, avg.period=15 )
# marginal.tbar.prcp.fall.avg <- lag.and.moving.average( marginal.tbar.prcp.fall, avg.period=15 )
# marginal.tbar.prcp.wint.avg <- lag.and.moving.average( marginal.tbar.prcp.wint, avg.period=15 )

# marginal.pbar.prcp.summ.avg <- lag.and.moving.average( marginal.pbar.prcp.summ, avg.period=15 )
# marginal.pbar.prcp.fall.avg <- lag.and.moving.average( marginal.pbar.prcp.fall, avg.period=15 )
# marginal.pbar.prcp.wint.avg <- lag.and.moving.average( marginal.pbar.prcp.wint, avg.period=15 )

# marginal.tbar.tmin.summ.avg <- lag.and.moving.average( marginal.tbar.tmin.summ, avg.period=15 )
# marginal.tbar.tmin.wint.avg <- lag.and.moving.average( marginal.tbar.tmin.wint, avg.period=15 )

# marginal.pbar.tmin.summ.avg <- lag.and.moving.average( marginal.pbar.tmin.summ, avg.period=15 )
# marginal.pbar.tmin.wint.avg <- lag.and.moving.average( marginal.pbar.tmin.wint, avg.period=15 )
####

# Generate lagged climate vars, for calculating delta Tbar and delta Pbar.
tmp <- array(NA, dim=c(dim(temps.avg)[1],1))
temps.avg.lag <- abind(tmp, temps.avg, along=2)
temps.avg.lag <- temps.avg.lag[ , 1:(dim(temps.avg.lag)[2]-1) ]
tmp <- array(NA, dim=c(dim(prcps.avg)[1],1))
prcps.avg.lag <- abind(tmp, prcps.avg, along=2)
prcps.avg.lag <- prcps.avg.lag[ , 1:(dim(prcps.avg.lag)[2]-1) ]


### I think this extra lag and moving average was an error, given that it was
## done above already. I think there may have been a conversation a long time
## ago where we thought the system did output a lagged average of marginals, which
## were then lagged and averaged again. But that appears to be wrong:
# Appears James does not already lag & moving average his cost components in the 
# projection system for mortality (which I had in my head that he did). See
# this comment from James and my following reply to clarify that the projection system
# does not lag & moving average the marginals terms (https://gitlab.com/ClimateImpactLab/Impacts/impact-calculations/-/issues/80#note_325202326)
# See also: https://gitlab.com/ClimateImpactLab/Impacts/impact-calculations/-/issues/197#note_685472791
if(1==0){
  # Lag and average my cost components. Now include gdd and kdd costs seperately.
  marginal.tbar.avg <- lag.and.moving.average( marginal.tbar.lag, avg.period=15 )
  marginal.pbar.avg <- lag.and.moving.average( marginal.pbar.lag, avg.period=15 )
  #### component costs
  marginal.tbar.temp.avg <- lag.and.moving.average( marginal.tbar.temp.lag, avg.period=15 )
  marginal.pbar.temp.avg <- lag.and.moving.average( marginal.pbar.temp.lag, avg.period=15 )
  
  marginal.tbar.tmin.avg <- lag.and.moving.average( marginal.tbar.tmin.lag, avg.period=15 )
  marginal.pbar.tmin.avg <- lag.and.moving.average( marginal.pbar.tmin.lag, avg.period=15 )
                   
  marginal.tbar.prcp.avg <- lag.and.moving.average( marginal.tbar.prcp.lag, avg.period=15 )
  marginal.pbar.prcp.avg <- lag.and.moving.average( marginal.pbar.prcp.lag, avg.period=15 )
  ####
}

## Compute costs

adpt.cost.tbar <- marginal.tbar.avg * ( temps.avg - temps.avg.lag )

adpt.cost.pbar <- marginal.pbar.avg * ( prcps.avg - prcps.avg.lag )
#### component costs
adpt.cost.tbar.temp <- marginal.tbar.temp.avg * ( temps.avg - temps.avg.lag )  
adpt.cost.pbar.temp <- marginal.pbar.temp.avg * ( prcps.avg - prcps.avg.lag )  

adpt.cost.tbar.tmin <- marginal.tbar.tmin.avg * ( temps.avg - temps.avg.lag )  
adpt.cost.pbar.tmin <- marginal.pbar.tmin.avg * ( prcps.avg - prcps.avg.lag ) 
                 
adpt.cost.tbar.prcp <- marginal.tbar.prcp.avg * ( temps.avg - temps.avg.lag )  
adpt.cost.pbar.prcp <- marginal.pbar.prcp.avg * ( prcps.avg - prcps.avg.lag ) 

# new add: winter wheat specific terms
# adpt.cost.tbar.temp.summ <- marginal.tbar.temp.summ.avg * ( temps.avg - temps.avg.lag )
# adpt.cost.tbar.temp.fall <- marginal.tbar.temp.fall.avg * ( temps.avg - temps.avg.lag )
# adpt.cost.tbar.temp.wint <- marginal.tbar.temp.wint.avg * ( temps.avg - temps.avg.lag )

# adpt.cost.pbar.temp.summ <- marginal.pbar.temp.summ.avg * ( prcps.avg - prcps.avg.lag ) 
# adpt.cost.pbar.temp.fall <- marginal.pbar.temp.fall.avg * ( prcps.avg - prcps.avg.lag ) 
# adpt.cost.pbar.temp.wint <- marginal.pbar.temp.wint.avg * ( prcps.avg - prcps.avg.lag ) 

# adpt.cost.tbar.prcp.summ <- marginal.tbar.prcp.summ.avg * ( temps.avg - temps.avg.lag ) 
# adpt.cost.tbar.prcp.fall <- marginal.tbar.prcp.fall.avg * ( temps.avg - temps.avg.lag ) 
# adpt.cost.tbar.prcp.wint <- marginal.tbar.prcp.wint.avg * ( temps.avg - temps.avg.lag ) 

# adpt.cost.pbar.prcp.summ <- marginal.pbar.prcp.summ.avg * ( prcps.avg - prcps.avg.lag ) 
# adpt.cost.pbar.prcp.fall <- marginal.pbar.prcp.fall.avg * ( prcps.avg - prcps.avg.lag ) 
# adpt.cost.pbar.prcp.wint <- marginal.pbar.prcp.wint.avg * ( prcps.avg - prcps.avg.lag ) 

# adpt.cost.tbar.tmin.summ <- marginal.tbar.tmin.summ.avg * ( temps.avg - temps.avg.lag ) 
# adpt.cost.tbar.tmin.wint <- marginal.tbar.tmin.wint.avg * ( temps.avg - temps.avg.lag ) 

# adpt.cost.pbar.tmin.summ <- marginal.pbar.tmin.summ.avg * ( prcps.avg - prcps.avg.lag ) 
# adpt.cost.pbar.tmin.wint <- marginal.pbar.tmin.wint.avg * ( prcps.avg - prcps.avg.lag ) 
####

adpt.cost <- adpt.cost.tbar + adpt.cost.pbar
#### component costs
adpt.cost.temp <- adpt.cost.tbar.temp + adpt.cost.pbar.temp
adpt.cost.tmin <- adpt.cost.tbar.tmin + adpt.cost.pbar.tmin
adpt.cost.prcp <- adpt.cost.tbar.prcp + adpt.cost.pbar.prcp

# new add: winter wheat specific terms
# adpt.cost.temp.summ <- adpt.cost.tbar.temp.summ + adpt.cost.pbar.temp.summ
# adpt.cost.temp.fall <- adpt.cost.tbar.temp.fall + adpt.cost.pbar.temp.fall
# adpt.cost.temp.wint <- adpt.cost.tbar.temp.wint + adpt.cost.pbar.temp.wint

# adpt.cost.prcp.summ <- adpt.cost.tbar.prcp.summ + adpt.cost.pbar.prcp.summ
# adpt.cost.prcp.fall <- adpt.cost.tbar.prcp.fall + adpt.cost.pbar.prcp.fall
# adpt.cost.prcp.wint <- adpt.cost.tbar.prcp.wint + adpt.cost.pbar.prcp.wint

# adpt.cost.tmin.summ <- adpt.cost.tbar.tmin.summ + adpt.cost.pbar.tmin.summ
# adpt.cost.tmin.wint <- adpt.cost.tbar.tmin.wint + adpt.cost.pbar.tmin.wint

####


# Set NA values to zero
adpt.cost[ is.na(adpt.cost) ] <- 0
# adpt.cost.tbar[ is.na(adpt.cost.tbar) ] <- 0
# adpt.cost.pbar[ is.na(adpt.cost.pbar) ] <- 0
#### component costs
adpt.cost.temp[ is.na(adpt.cost.temp) ] <- 0
adpt.cost.tmin[ is.na(adpt.cost.tmin) ] <- 0
adpt.cost.prcp[ is.na(adpt.cost.prcp) ] <- 0

# new add: winter wheat specific terms
# adpt.cost.temp.summ[ is.na(adpt.cost.temp.summ) ] <- 0
# adpt.cost.temp.fall[ is.na(adpt.cost.temp.fall) ] <- 0
# adpt.cost.temp.wint[ is.na(adpt.cost.temp.wint) ] <- 0

# adpt.cost.prcp.summ[ is.na(adpt.cost.prcp.summ) ] <- 0
# adpt.cost.prcp.fall[ is.na(adpt.cost.prcp.fall) ] <- 0
# adpt.cost.prcp.wint[ is.na(adpt.cost.prcp.wint) ] <- 0

# adpt.cost.tmin.summ[ is.na(adpt.cost.tmin.summ) ] <- 0
# adpt.cost.tmin.wint[ is.na(adpt.cost.tmin.wint) ] <- 0
####

# Set 2015 and earlier to zero
baseline <- which(year.avg == 2015)
adpt.cost[ , 1:baseline ] <- 0
# adpt.cost.tbar[ , 1:baseline ] <- 0
# adpt.cost.pbar[ , 1:baseline ] <- 0
#### component costs
adpt.cost.temp[ , 1:baseline ] <- 0
adpt.cost.tmin[ , 1:baseline ] <- 0
adpt.cost.prcp[ , 1:baseline ] <- 0

# new add: winter wheat specific terms
# adpt.cost.temp.summ[ , 1:baseline ] <- 0
# adpt.cost.temp.fall[ , 1:baseline ] <- 0
# adpt.cost.temp.wint[ , 1:baseline ] <- 0

# adpt.cost.prcp.summ[ , 1:baseline ] <- 0
# adpt.cost.prcp.fall[ , 1:baseline ] <- 0
# adpt.cost.prcp.wint[ , 1:baseline ] <- 0

# adpt.cost.tmin.summ[ , 1:baseline ] <- 0
# adpt.cost.tmin.wint[ , 1:baseline ] <- 0
####


# Cumulative of annual marginal cost terms
cum.cost <- rowCumsums( adpt.cost )
# cum.cost.tbar <- rowCumsums( adpt.cost.tbar )
# cum.cost.pbar <- rowCumsums( adpt.cost.pbar )
#### component costs
cum.cost.temp <- rowCumsums( adpt.cost.temp )
cum.cost.tmin <- rowCumsums( adpt.cost.tmin )
cum.cost.prcp <- rowCumsums( adpt.cost.prcp )

# new add: winter wheat specific terms
# cum.cost.temp.summ <- rowCumsums( adpt.cost.temp.summ )
# cum.cost.temp.fall <- rowCumsums( adpt.cost.temp.fall )
# cum.cost.temp.wint <- rowCumsums( adpt.cost.temp.wint )

# cum.cost.prcp.summ <- rowCumsums( adpt.cost.prcp.summ )
# cum.cost.prcp.fall <- rowCumsums( adpt.cost.prcp.fall )
# cum.cost.prcp.wint <- rowCumsums( adpt.cost.prcp.wint )

# cum.cost.tmin.summ <- rowCumsums( adpt.cost.tmin.summ )
# cum.cost.tmin.wint <- rowCumsums( adpt.cost.tmin.wint )
####


# Write .netcdf output

print('------------------')
print(paste0('Writing costs for ', crop, ' under model ', model, ' / RCP ', rcp, ' / SSP', ssp, ' / IAM-',iam))
print('------------------')

my.regions <- as.character(regions)
max.region.chars <- max(nchar(my.regions))
years <- as.numeric(as.character(year.avg))

dim_nchar <- ncdim_def('nchar', units='', 1:max.region.chars, create_dimvar=FALSE)
dim_regions <- ncdim_def('region', units='', 1:length(my.regions), create_dimvar=FALSE)
dim_time <- ncdim_def('year',  units='', years)

var_regions <- ncvar_def(name = 'regions', units='', dim=list(dim_nchar, dim_regions), prec='char')
var_years <- ncvar_def(name = 'years', units='', dim=list(dim_time))
var_costs <- ncvar_def(name = 'adpt.cost.cuml', units='log_yield', dim=list(dim_regions, dim_time))
# var_costs_tbar <- ncvar_def(name = 'adpt.cost.tbar', units='log_yield', dim=list(dim_regions, dim_time))
# var_costs_pbar <- ncvar_def(name = 'adpt.cost.pbar', units='log_yield', dim=list(dim_regions, dim_time))
#### component costs
var_costs_temp <- ncvar_def(name = 'adpt.cost.temp.cuml', units='log_yield', dim=list(dim_regions, dim_time))
var_costs_tmin <- ncvar_def(name = 'adpt.cost.tmin.cuml', units='log_yield', dim=list(dim_regions, dim_time))
var_costs_prcp <- ncvar_def(name = 'adpt.cost.prcp.cuml', units='log_yield', dim=list(dim_regions, dim_time))

# new add: winter wheat specific terms
# var_costs_temp_summ <- ncvar_def(name = 'adpt.cost.temp.summ.cuml', units='log_yield', dim=list(dim_regions, dim_time))
# var_costs_temp_fall <- ncvar_def(name = 'adpt.cost.temp.fall.cuml', units='log_yield', dim=list(dim_regions, dim_time))
# var_costs_temp_wint <- ncvar_def(name = 'adpt.cost.temp.wint.cuml', units='log_yield', dim=list(dim_regions, dim_time))

# var_costs_prcp_summ <- ncvar_def(name = 'adpt.cost.prcp.summ.cuml', units='log_yield', dim=list(dim_regions, dim_time))
# var_costs_prcp_fall <- ncvar_def(name = 'adpt.cost.prcp.fall.cuml', units='log_yield', dim=list(dim_regions, dim_time))
# var_costs_prcp_wint <- ncvar_def(name = 'adpt.cost.prcp.wint.cuml', units='log_yield', dim=list(dim_regions, dim_time))

# var_costs_tmin_summ <- ncvar_def(name = 'adpt.cost.tmin.summ.cuml', units='log_yield', dim=list(dim_regions, dim_time))
# var_costs_tmin_wint <- ncvar_def(name = 'adpt.cost.tmin.wint.cuml', units='log_yield', dim=list(dim_regions, dim_time))
####

# vars <- list(var_regions, var_years, var_costs)
#### changed to add component costs (originally was 'vars <- list(var_regions, var_years, var_costs, var_costs_tbar, var_costs_pbar)')
# vars <- list(var_regions, var_years, var_costs, var_costs_tbar, var_costs_pbar, var_costs_temp, var_costs_tmin, var_costs_prcp,
#              var_costs_temp_summ, var_costs_temp_fall, var_costs_temp_wint,
#              var_costs_prcp_summ, var_costs_prcp_fall, var_costs_prcp_wint,
#              var_costs_tmin_summ, var_costs_tmin_wint)
vars <- list(var_regions, var_years, var_costs, var_costs_temp, var_costs_tmin, var_costs_prcp)
####

# Filepath for cost output
f.out <- paste0(outpath, '/adaptation_costs.nc4')
costs_nc <- nc_create(f.out, vars, force_v4=TRUE)

# print('cumulative costs')
# print(cum.cost[1:5,1:5])
# print(cum.cost[1000:1005,50:55])

ncvar_put(costs_nc, var_regions, my.regions)
ncvar_put(costs_nc, var_years, years)
ncvar_put(costs_nc, var_costs, cum.cost)
# ncvar_put(costs_nc, var_costs_tbar, cum.cost.tbar)
# ncvar_put(costs_nc, var_costs_pbar, cum.cost.pbar)
#### component costs
ncvar_put(costs_nc, var_costs_temp, cum.cost.temp)
ncvar_put(costs_nc, var_costs_tmin, cum.cost.tmin)
ncvar_put(costs_nc, var_costs_prcp, cum.cost.prcp)

# new add: winter wheat specific terms
# ncvar_put(costs_nc, var_costs_temp_summ, cum.cost.temp.summ)
# ncvar_put(costs_nc, var_costs_temp_fall, cum.cost.temp.fall)
# ncvar_put(costs_nc, var_costs_temp_wint, cum.cost.temp.wint)

# ncvar_put(costs_nc, var_costs_prcp_summ, cum.cost.prcp.summ)
# ncvar_put(costs_nc, var_costs_prcp_fall, cum.cost.prcp.fall)
# ncvar_put(costs_nc, var_costs_prcp_wint, cum.cost.prcp.wint)

# ncvar_put(costs_nc, var_costs_tmin_summ, cum.cost.tmin.summ)
# ncvar_put(costs_nc, var_costs_tmin_wint, cum.cost.tmin.wint)
####

if (encode_regions) ncatt_put(costs_nc, 'regions', '_Encoding', 'ascii')

# Global attributes, which generate.aggregate copies into the aggregated file
ncatt_put(costs_nc, 0, 'description', paste0('Adaptation costs for ', crop))
ncatt_put(costs_nc, 0, 'version', 'tmp_and_prcp_costs-bugfixed')
ncatt_put(costs_nc, 0, 'author', 'Climate Impact Lab')
ncatt_put(costs_nc, 0, 'dependencies', incpath)

nc_close(costs_nc)


print("----------- DONE DONE DONE ------------")

