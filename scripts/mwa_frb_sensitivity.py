# import lfaa_requirements
import sys
import math

# options :
from optparse import OptionParser,OptionGroup


def parse_options(idx=0):
   usage="Usage: %prog [options]\n"
   usage+='\tSensitivity of the MWA telescope\n'
   parser = OptionParser(usage=usage,version=1.00)
   parser.add_option('--n_polarisations','--n_pols','--npols',dest="n_polarisations",default=2, help="Number of polarisations [default %default]",metavar="int")
   parser.add_option('--sefd',dest="sefd",default=50931.8, help="MWA SEFD [default %default]",type="float")
   parser.add_option('-c','--coherent',action="store_true",dest="coherent",default=False,help="Coherent sum [default %default]")
   parser.add_option('--lofar_rate',dest="lofar_rate",default=False,action="store_true", help="Use LOFAR rate [default %default]")
   parser.add_option('--lofar_rate_value',dest="lofar_rate_value",default=3, help="Use LOFAR rate value [default %default]",type="int")
   parser.add_option('--scaling_index',dest="scaling_index",default=-2.1, help="Use LOFAR rate value [default %default]",type="float")
   parser.add_option('--euclidean',dest="euclidean",default=False,action="store_true", help="Euclidean source count scaling [default %default]")
   parser.add_option('--verb',dest="verb",default=True,action="store_true", help="Verbosity level [default %default]")

   
   (options, args) = parser.parse_args(sys.argv[idx:])
   
   return (options, args)


def frb_rate( fluence_min, min_elev_deg=20, scaling_index=-2.1, verb=False ):
   # Shannon et al. 2018 
   # 37 +/- 8 /day/sky 
   # above threshold = 26 Jy ms (w/1.26 ms)^{-1/2}
   
   # min_elevation = 20 degrees is what is sensible for the EDA2/AAVS2 all-sky images:
   
   
   per_sky_per_day = 37*(pow( (fluence_min/26.00) , scaling_index ))
   per_sky_per_year = per_sky_per_day*365
   
   if verb :
      print("per_sky_per_day = %.4f FRBs / sky / day" % (per_sky_per_day))
   
   # multiply by the fraction of the sky corresponding to elevation range (min_elevation,90) [deg]
   min_elev_rad = min_elev_deg * (math.pi / 180.00)    
   sky_fraction = 0.5*(1.00 - math.sin( min_elev_rad ) )
#   print("DEBUG : min_elevation = %.2f [deg] -> fraction = %.5f" % (min_elev_deg,sky_fraction))
   per_sky_per_day = per_sky_per_day * sky_fraction
   per_sky_per_year = per_sky_per_year * sky_fraction
   
   return (per_sky_per_day,per_sky_per_year)


def frb_rate_OLD( fluence_min, min_elev_deg=40 ):
   # Shannon et al. 2018 
   # 37 +/- 8 /day/sky 
   # above threshold = 26 Jy ms (w/1.26 ms)^{-1/2}
   
   # min_elevation = 20 degrees is what is sensible for the EDA2/AAVS2 all-sky images:
         
   per_sky_per_day = 37*(pow( (fluence_min/26.00) , (-2.1) ))
   per_sky_per_year = per_sky_per_day*365
   
   # multiply by the fraction of the sky corresponding to elevation range (min_elevation,90) [deg]
   min_elev_rad = min_elev_deg * (math.pi / 180.00)    


#    sky_fraction = 0.5*(1.00 - math.sin( min_elev_rad ) )
   # MWA sky fraction assuming 30x30 = 900 deg^2 FoV :   
   fov_deg2 = (30.00*30.00)*(math.pi/180.00)*(math.pi/180.00)
   sky_fraction = fov_deg2 / (4.00*math.pi)

#   print("DEBUG : min_elevation = %.2f [deg] -> fraction = %.5f" % (min_elev_deg,sky_fraction))
   per_sky_per_day = per_sky_per_day * sky_fraction
   per_sky_per_year = per_sky_per_year * sky_fraction
   
   return (per_sky_per_day,per_sky_per_year)

# from paper : https://ui.adsabs.harvard.edu/abs/2020arXiv201208348P/abstract
# combining our results with previous upper-limits on the all-sky FRB rate at 150 MHz, we find that there are 3-450 FRBs/sky/day above 50 Jy ms at 90% confidence.
# index=-2.1 as in Ryan Shannon et al. (2018) , Euclidean space is -1.5 = -3/2 
def lofar_frb_rate( fluence_min, min_elev_deg=20, lofar_rate=3, cut_off_fluence=50, verb=False, scaling_index=-2.1 ):

   per_sky_per_day =  lofar_rate*(pow( (float(fluence_min)/float(cut_off_fluence)) , scaling_index ))
   per_sky_per_year = per_sky_per_day*365

   if verb :
      print("per_sky_per_day = %.4f FRBs / sky / day" % (per_sky_per_day))


   # multiply by the fraction of the sky corresponding to elevation range (min_elevation,90) [deg]
#   min_elev_rad = min_elev_deg * (math.pi / 180.00)
#   sky_fraction = 0.5*(1.00 - math.sin( min_elev_rad ) )
   fov_deg2 = (30.00*30.00)*(math.pi/180.00)*(math.pi/180.00)
   sky_fraction = fov_deg2 / (4.00*math.pi)

   per_sky_per_day = per_sky_per_day * sky_fraction
   per_sky_per_year = per_sky_per_year * sky_fraction

   return (per_sky_per_day,per_sky_per_year)



if __name__ == "__main__":
    # constants :
    # Boltzman :
    k = 1380 # in Jy units

    freq_mhz = 160.00
    if len(sys.argv) >= 1 :
       freq_mhz = float( sys.argv[1] )

    inttime=1000.00 # ms 
#    if len(sys.argv) >= 3 :
#       inttime = float( sys.argv[2] )
       
#    bw_chan=(400.00/512.00)*(32.00/27.00) # single channel :    
    bw_chan = 1.28 # MHz 
    n_chan = 24
    if len(sys.argv) >= 3 :
       n_chan = int( sys.argv[2] )
    bw = bw_chan*n_chan   

    (options, args) = parse_options()

    if options.euclidean :
       options.scaling_index = -1.5

    print("###############################")
    print("PARAMETERS:")
    print("###############################")
    print("Frequency        = %.2f MHz" % (freq_mhz))
    print("Integration time = %.2f ms" % (inttime))
    print("N_channels       = %d -> %d x %.2f MHz = %.2f MHz" % (n_chan,n_chan,bw_chan,bw))
    print("N polarisations  = %d" % (options.n_polarisations))
    print("Coherent         = %s" % (options.coherent))
    print("Use LOFAR Pastor-Marazuela (2020) values = %s [value = %d / day / sky]" % (options.lofar_rate,options.lofar_rate_value))
    print("Source count scaling index = %.4f (Euclidean flag = %s)" % (options.scaling_index,options.euclidean))
    print("###############################")
           
    
#    aot_station = lfaa_requirements.lfaa_per_station( freq_mhz , interpolation_kind='cubic')
#    sefd_station = lfaa_requirements.aot2sefd( aot_station )
    sefd_station = options.sefd
    aot_station  = (2*k)/sefd_station

    
    n_ant = 128
    n_baselines = n_ant*(n_ant)/2
    
    n = n_ant
    if options.coherent :
       n = n_baselines    
    sefd_telescope = sefd_station / math.sqrt(n)       

    
    print("Frequency = %.2f MHz" % (freq_mhz))
    print("Station A/T = %.4f m^2/K" % (aot_station))
    print("Station SEFD = %.4f m^2/K" % (sefd_station))
    print("Telescope SEFD = %.4f m^2/K" % (sefd_telescope))

 
    bw_hz = bw*1000000.00
    
    for n_sigma in (3,10) :
       outname = "sens_nchan%d_freq%.2fMHz_%.1fsigma.txt" % (n_chan,freq_mhz,n_sigma)
       out_f = open( outname , "w" )
       
       print("")
       print("\tThreshold = %d sigma:" % (n_sigma))
    
       for inttime_ms in (1,10,50,100,150,200,300,500,762,1000,2000,2286,3000,4000,5000,10000) : 
          inttime_sec = inttime_ms/1000.00
              
          sens_jy = sefd_station / math.sqrt( bw_hz * inttime_sec * options.n_polarisations * n )
          sens_mjy = sens_jy*1000.00
       
#       n_sigma=3
#       limit_ms_3sigma = sens_jy*n_sigma*inttime_sec
#       limit_ms_3sigma2 = sefd_station * math.sqrt( inttime_sec / bw_hz ) * n_sigma             
#       print("\t%.1f ms : %.2f mJy -> 3sigma limit = %.2f [Jy sec] (vs. %.2f)" % (inttime_ms,sens_mjy,limit_ms_3sigma,limit_ms_3sigma2))
    

          limit_ms_Nsigma = sens_jy*n_sigma*inttime_ms
          if options.lofar_rate :
             (per_sky_per_day,per_sky_per_year) = lofar_frb_rate( limit_ms_Nsigma, lofar_rate=options.lofar_rate_value, scaling_index=options.scaling_index , verb=options.verb )
          else :
             (per_sky_per_day,per_sky_per_year) = frb_rate( limit_ms_Nsigma, scaling_index=options.scaling_index, verb=options.verb  )
          
          print("\t\t%.1f ms : %.2f mJy -> %dsigma limit = %.2f [Jy msec] -> %.5f / day / sky or %.5f / year / sky" % (inttime_ms,sens_mjy,n_sigma,limit_ms_Nsigma,per_sky_per_day,per_sky_per_year))
          
          line = "%1.f %.2f %.5f %.5f %.2f %.1f\n" % (inttime_ms,limit_ms_Nsigma,per_sky_per_day,per_sky_per_year,sens_mjy,n_sigma)
          out_f.write( line )
         
    
#       n_sigma=10
#       limit_ms_3sigma = sens_jy*n_sigma*inttime_ms
#       print("\t%.1f ms : %.2f mJy -> %dsigma limit = %.2f [Jy msec]" % (inttime_ms,sens_mjy,n_sigma,limit_ms_3sigma))


       print("")    
       out_f.close()
    