#!/usr/bin/env python

"""
Script for calculating A/T for MWA 
Script calling function primarybeammap_tant.py to calculate antenna temperature according to MWA beam model (analytic, AEE or FEE) and scaled Haslam map
Example usage:
python ./mwa_sensitivity.py -b 18,13,8,3,17,12,7,2,16,11,6,1,15,10,5,0 -c 169 -p all -g 0  -m full_EE
python ./mwa_sensitivity.py -c 169 -p all -g 0  -m full_EE

Using METAFITS :
 getmeta! OBSID 
 python ./mwa_sensitivity.py --metafits OBSID.metafits -p all -m full_EE --gps OBSID -c 121 --bandwidth 30720000 --inttime 120

Starting version by Marcin Sokolowski

main task is:
make_primarybeammap()

This is the script interface to the functions and modules defined in MWA_Tools/src/primarybeamap.py

"""

import errno
import math
from optparse import OptionParser
import os
import sys

from astropy.io import fits as pyfits

import numpy as np
from scipy.interpolate import interp1d # for interpolation of receiver temperature


from mwa_pb.primarybeammap_tant import contourlevels, get_beam_power, logger, make_primarybeammap
from mwa_pb import mwa_sweet_spots
from mwa_pb import metadata


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST:
            pass
        else:
            raise

    # as in loogbook/paper/eda_lightcurve_and_trcv.odt Ill. 13:


# /home/msok/Desktop/EDA/data/2016-07/20160703/HASLAM/WithSun_and_BeamformingErrors/BIGHORNS/images/final/paper/trcv_vs_freq_lst_13-17_hours.png
# root [1] .x plotspec_freq_errxy.C("trcv_vs_freq_lst_range_13_17_hours.txt")
# Fitted : [0]*(150/x)^[1]
def trcv_from_skymodel_with_err(freq_mhz):
    # not to go below 50K (as fitting might be tricky)
    #   if trcv < 50 or freq_mhz>160 :
    #   if freq_mhz > 160 :
    #      return 50

    #   x=[55.0,65.0,75.0,85.0,95.0,105.0,115.0,125.0,135.0,145.0,155.0,165.0,175.0,185.0,195.0,205.0]
    #   y=[3722.55055596,1421.83480972,655.8033454,409.69506365,356.59552554,293.4326318,200.26593869,163.91940732,157.46121101,112.19530177,51.14849704,68.56693587,28.33318976,43.72596282,34.41633474,62.76422256]
    #   tlna_cubic = interp1d(x, y, kind='cubic')
    #   trcv = tlna_cubic(freq_mhz)
    index = 3.46114
    trcv = 82.4708 * math.pow((150.00 / freq_mhz), index)

    if trcv < 50 or freq_mhz > 160:
        trcv = 50

    # /home/msok/Desktop/EDA/loogbook/paper/T_rcv/eda_paper_lightcurve_and_trcv_FINAL_MORE_POINTS.odt
    if freq_mhz > 200:
        trcv = 80

    return trcv

# based on Daniel's paper 2020 : Noise Temperature of Phased Array Radio Telescope: The Murchison Widefield Array and the Engineering Development Array, Ung et al, 2020, IEEE 
# less /home/msok/Desktop/MWA/papers/2020/Daniel/trcv_vs_freq.txt.txt 
def trcv_daniel_paper_2020( freq_mhz ) :
   x = [ 50.1336,52.4987,54.5253,58.5773,60.6017,63.2964,65.3203,68.3472,72.3884,73.7374,77.7740,82.1462,85.8443,89.2056,92.5666,96.5994,100.969,108.701,114.417,120.802,127.187,133.237,140.296,148.868,153.068,158.949,165.839,170.711,175.079,178.271,184.821,189.524,192.883,197.082,204.806,210.515,217.567,221.091,224.953,228.143,232.341,235.027,238.218,241.913,243.928,247.957,249.805,251.653,254.509,255.181,258.371,264.081,270.128,274.495,282.221,286.421,291.964,296.332,301.036,304.061,308.597,311.790,314.646,320.526,326.740 ]
   y = [ 2363.92,1600.02,1168.37,643.601,501.566,408.215,321.595,291.723,220.082,189.092,162.481,141.139,130.839,123.949,118.702,113.679,105.386,90.5671,80.3998,74.5398,70.6221,65.4739,58.1265,49.6844,48.3628,45.5723,41.7958,40.6851,40.0350,38.9687,40.7059,41.3804,40.9391,41.8431,45.1556,48.7268,52.2987,57.6677,60.8893,62.2315,65.7089,69.0016,69.0096,69.0188,70.9207,75.6996,76.5301,75.7098,74.4959,73.6942,76.9700,80.3988,80.4164,80.4291,81.7709,79.5959,80.0447,79.6244,77.9293,75.0352,71.8618,69.9478,68.8263,67.3640,68.1138 ]
   l = len(x)
   
   
   if freq_mhz < 50 :
      return y[0]
      
   if freq_mhz > 326 :
      return y[l-1]
      
   tlna_cubic = interp1d(x, y, kind='cubic')
   trcv = tlna_cubic(freq_mhz)
   
   return trcv    
   


def calculate_sensitivity(options, freq, delays, gps, trcv_type, T_rcv, size, dirname, model, plottype, extension,
                          pointing_az_deg=0,
                          pointing_za_deg=0,
                          add_sources=False,
                          zenithnorm=True,
                          antnum=128,
                          inttime=120,
                          bandwidth=1280000,                          
                          incoherent=False ):
    freq_mhz = freq / 1e6
    if options.pulsar_observing_time <= 0 :
       options.pulsar_observing_time = inttime
    print('pulsar_observing_time = %.2f [sec], frequency=%.2f -> delays=%s' % (options.pulsar_observing_time,freq, delays))

    # if trcv_type',default='trcv_from_skymodel_with_err
#    if trcv_type != "value":
#        if trcv_type == "trcv_from_skymodel_with_err":
#            T_rcv = trcv_from_skymodel_with_err(freq_mhz)
#            print("T_rcv calculated from trcv_from_skymodel_with_err = %.2f K" % (T_rcv))
    T_rcv = trcv_daniel_paper_2020( freq_mhz )
    print("T_rcv calculated from trcv_daniel_paper_2020( %.2f MHz ) = %.2f K" % (freq_mhz,T_rcv))

    result = make_primarybeammap(gps, delays, freq,
                                 model=model,
                                 plottype=plottype,
                                 extension=extension,
                                 resolution=size,
                                 directory=dirname,
                                 zenithnorm=zenithnorm,
                                 b_add_sources=add_sources)
    (beamsky_sum_XX, beam_sum_XX, Tant_XX, beam_dOMEGA_sum_XX, beamsky_sum_YY, beam_sum_YY, Tant_YY,
     beam_dOMEGA_sum_YY) = result

    beams = get_beam_power(delays, freq,
                           model=model,
                           pointing_az_deg=pointing_az_deg,
                           pointing_za_deg=pointing_za_deg,
                           zenithnorm=zenithnorm)

    gain_XX = beams['XX'] / (beam_dOMEGA_sum_XX / (4.00 * math.pi))
    gain_YY = beams['YY'] / (beam_dOMEGA_sum_YY / (4.00 * math.pi))

    ant_efficiency = 1.00
    aeff_XX = (7161.97 / (freq_mhz * freq_mhz)) * (gain_XX * ant_efficiency)
    aeff_YY = (7161.97 / (freq_mhz * freq_mhz)) * (gain_YY * ant_efficiency)

    T_sys_XX = (Tant_XX + T_rcv)
    T_sys_YY = (Tant_YY + T_rcv)

    sens_XX = aeff_XX / T_sys_XX
    sens_YY = aeff_YY / T_sys_YY

    sefd_XX = (2760.00 / sens_XX)  # 2k/(A/T)
    sefd_YY = (2760.00 / sens_YY)  # 2k/(A/T)

    antnum_minus1 = (antnum - 1)
    if antnum == 1 :
       antnum_minus1 = 1

    object="images"
    if options.incoherent :
       noise_XX = sefd_XX / math.sqrt(bandwidth * inttime * antnum )
       noise_YY = sefd_YY / math.sqrt(bandwidth * inttime * antnum )    
       object="incoherent beam"
    else :
       noise_XX = sefd_XX / math.sqrt(bandwidth * inttime * antnum * antnum_minus1)
       noise_YY = sefd_YY / math.sqrt(bandwidth * inttime * antnum * antnum_minus1)

    print("%.2f Hz :" % (freq))

    lstring = "\t\tXX (%.2f MHz) : T_ant_XX = %.2f  = (%.8f / %.8f) , beam(%.4f,%.4f)=%.8f , gain=%.8f , aeff=%.8f, "
    lstring += "sensitivity (A/T) = %.20f -> SEFD_XX = %.2f Jy -> noise_XX = %.4f Jy"
    params = (freq_mhz, Tant_XX, beamsky_sum_XX, beam_sum_XX, pointing_az_deg, pointing_za_deg, beams['XX'], gain_XX,
              aeff_XX, sens_XX, sefd_XX, noise_XX)
    print(lstring % params)

    lstring = "\t\tYY (%.2f MHz) : T_ant_YY = %.2f  = (%.8f / %.8f) , beam(%.4f,%.4f)=%.8f , gain=%.8f , aeff=%.8f, "
    lstring += "sensitivity (A/T) = %.20f -> SEFD_YY = %.2f Jy -> noise_YY = %.4f Jy"
    params = (freq_mhz, Tant_YY, beamsky_sum_YY, beam_sum_YY, pointing_az_deg, pointing_za_deg, beams['YY'], gain_YY,
              aeff_YY, sens_YY, sefd_YY, noise_YY)
    print(lstring % params)
    
    # WARNING : should be more complicated than this (TO-BE-UPDATED) :
    noise_I = 0.5*math.sqrt( noise_XX*noise_XX + noise_YY*noise_YY )
    SEFD_I  = 0.5*math.sqrt( sefd_XX*sefd_XX + sefd_YY*sefd_YY )

    print("Noise expected in XX %s = %.4f Jy" % (object,noise_XX))
    print("Noise expected in YY %s = %.4f Jy" % (object,noise_YY))
    print("Noise expected in Stokes I %s = %.4f Jy (simple formula only !) , SEFD_I = %.4f Jy" % (object,noise_I,SEFD_I))
    
    if options.show_snr :
       pulsar_peak_flux = options.pulsar_mean_flux * (options.pulsar_period / options.pulsar_pulse_width)
       if options.pulsar_peak_flux > 0 :
           pulsar_peak_flux = options.pulsar_peak_flux
           
       snr = pulsar_peak_flux / noise_I
       
       print("Pulsar peak flux = %.3f [mJy] -> snr = %.2f (SNR OF SINGLE PULSES)" % (pulsar_peak_flux*1000.00,snr))
       
    
    # as in /home/msok/github/station_beam/python/lfaa_sensitivity.py
    # sens_jy = SEFD_I / math.sqrt( bandwidth * inttime )
    sens_jy = noise_I # have to use noise_I which is calculated for incoherent sum 
    
    # FRB width = 10ms :
    FRB_width=0.010 # second (10ms)
    
    if inttime >= FRB_width :    
        print("INFO : calculating FRB sensitivity for integration time = %.2f [ms] wider than typical FRB width = %.2f [ms]" % (inttime*1000,FRB_width*1000))
    else :
        print("INFO : calculating FRB sensitivity for integration time = %.2f [ms] shorter than typical FRB width = %.2f [ms]" % (inttime*1000,FRB_width*1000))

        
    for n_sigma in [5,10,20] :       
       if inttime >= FRB_width :    
          limit_ms_Nsigma = sens_jy*n_sigma*inttime*1000.00 # limit in Jy ms :
       else :
          limit_ms_Nsigma = sens_jy*n_sigma*FRB_width*1000.00 # limit in Jy ms :  
         
       print("FRB limit %d sigma is %.4f Jy ms" % (n_sigma,limit_ms_Nsigma))
    
    if options.n_phase_bins >= 1 :
       print("Calculating noise in a folded profile for number of bins = %d" % (options.n_phase_bins))
       # n_p = 2 # 2 polarisations 
       inttime_per_bin = options.pulsar_observing_time / options.n_phase_bins
       if options.incoherent :
          noise_folded_i = SEFD_I/math.sqrt(bandwidth*inttime_per_bin*antnum)
       else :
          noise_folded_i = SEFD_I/math.sqrt(bandwidth*inttime_per_bin*antnum * antnum_minus1)
       print("Expected noise in a folded profile (per phase bin) = %.3f [mJy] = %.6f [Jy]" % ((noise_folded_i*1000.00),noise_folded_i))
       
       noise_folded_total_obstime_i = 0.00
       if options.incoherent :
          noise_folded_total_obstime_i = SEFD_I/math.sqrt(bandwidth*options.pulsar_observing_time*antnum)
       else :
          noise_folded_total_obstime_i = SEFD_I/math.sqrt(bandwidth*options.pulsar_observing_time*antnum * antnum_minus1)
       print("Expected noise in full %.2f [sec] observation integrated =  %.3f [mJy] = %.6f [Jy]" % (options.pulsar_observing_time,(noise_folded_total_obstime_i*1000.00),noise_folded_total_obstime_i))

       
       if options.show_snr :
          pulsar_peak_flux = options.pulsar_mean_flux * (options.pulsar_period / options.pulsar_pulse_width)
          if options.pulsar_peak_flux > 0 :
              pulsar_peak_flux = options.pulsar_peak_flux
          snr = pulsar_peak_flux / noise_folded_i

          print("Pulsar peak flux = %.3f [mJy] -> snr = %.2f (SNR OF FOLDED PROFILE)" % (pulsar_peak_flux*1000.00,snr))


    return (aeff_XX, T_sys_XX, sens_XX, sefd_XX, noise_XX, beams['XX'], aeff_YY, T_sys_YY, sens_YY, sefd_YY, noise_YY, beams['YY'] )


def main():
    usage = "Usage: %prog [options]\n"
    usage += "\tCalculates MWA sensitivity for given observing parameters\n"
    usage += "\tCreates an image of the 408 MHz sky (annoted with sources) that includes contours for the MWA primary beam\n"
    usage += "\tThe beam is monochromatic, and is the sum of the XX and YY beams\n"
    usage += "\tThe beamformer delays must be specified\n"
    usage += "\tBeamformer delays should be separated by commas\n"
    usage += "\tFrequency is in MHz, or a coarse channel number (can also be comma-separated list)\n"
    usage += "\tDefault is to plot centered on RA=0, but if -r/--racenter, will center on LST\n"
    usage += "\tContours will be plotted at %s of the peak\n" % contourlevels
    usage += "\tExample:\tpython ./mwa_sensitivity.py -c 145 --model 2016 --pointing_za_deg 5 --pointing_az_deg 0 --antnum=60 --inttime=120 --trcv_type=trcv_from_skymodel_with_err -p all --gridpoint=0\n\n"

    parser = OptionParser(usage=usage)
    #  parser.add_option('-d', '--datetimestring', dest="datetimestring", default=None,
    #                    help="Compute for <DATETIMESTRING> (YYYYMMDDhhmmss)",
    #                    metavar="DATETIMESTRING")
    parser.add_option('-c', '--channel', '--freq_cc', dest='channel', default=None,
                      help='Center channel(s) of observation')
    parser.add_option('-f', '--frequency', '--freq_mhz', dest='frequency', default=None,
                      help='Center frequency(s) of observation [MHz]')
    parser.add_option('-b', '--beamformer', '--delays', dest='delays', default="0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
                      # default zenith pointing
                      help='16 beamformer delays separated by commas')
    parser.add_option('--metafits', dest='metafits', default=None,
                      help="FITS file to get delays from (can be metafits)")
    #  parser.add_option('-D', '--date', dest='date', default=None, help='UT Date')
    #  parser.add_option('-t', '--time', dest='time', default=None, help='UT Time')
    parser.add_option('-g', '--gps', '--obsid', dest='gps', default=0, help='GPS time')
    parser.add_option('-m', '--model', dest='model', default='analytic',
                      help='beam model: analytic (2014), advanced (2015), full_EE (2016), full_EE_AAVS05')
    parser.add_option('-p', '--plottype', dest='plottype', default='beamsky',
                      help='Type of plot: all, beam, sky, beamsky, beamsky_scaled')
    parser.add_option('--title', dest='title', default=None, help='Plot title')
    parser.add_option('-e', '--ext', dest='extension', default='png', help='Plot extension [default=%default]')
    #    parser.add_option('-r','--racenter',action="store_true",dest="center",default=False,help="Center on LST?")
    parser.add_option('-n', '--no_zenith_norm', action="store_false", dest="zenithnorm", default=True,
                      help="Normalise to zenith (default True)")
    parser.add_option('--size', dest='size', default=1000, type=int, help='Resolution of created beam file')
    parser.add_option('--dir', dest='dir', default=None, help='output directory')
    parser.add_option('--pointing_za_deg', '--za', dest='pointing_za_deg', default=None, help='Pointing za [deg]', type=float)
    parser.add_option('--pointing_az_deg', '--az', dest='pointing_az_deg', default=None, help='Pointing az [deg]', type=float)
    parser.add_option('--pointing_elev_deg', '--elev', dest='pointing_elev_deg', default=90.00, help='Pointing elevation [deg]', type=float)
    parser.add_option('--pointing_ra_deg', '--ra', dest='pointing_ra_deg', default=None, help='Pointing RA [deg]', type=float)
    parser.add_option('--pointing_dec_deg', '--dec', dest='pointing_dec_deg', default=None, help='Pointing DEC [deg]', type=float)
    parser.add_option('-r', '--t_rcv', dest='t_rcv', default=0, help='Receiver noise temperature', type=float)
    parser.add_option('--gridpoint', dest='gridpoint', default=-1, help='Gridpoint number', type=int)
    
    # different options of summation (default interferometry):
    # incoherent sum on N antennas :
    parser.add_option('--incoherent', '--ic', action="store_true", dest="incoherent", default=False, help="Sensitivity of incoherent sum [default %default]")
    # folding pulsars :
    parser.add_option('--n_phase_bins', '--n_bins', dest='n_phase_bins', default=1, help='Number of phase bins when folding pulsar observations [default %default]', type=int)    
    parser.add_option('--pulsar_observing_time', dest='pulsar_observing_time', default=-1, type=float, help='Total pulsar observing time in seconds [default %default sec]')
    parser.add_option('--pulsar_mean_flux', '--psr_mean_flux', dest='pulsar_mean_flux', default=2.37, help='Pulsar mean flux density in Jy [default %default - for B0950+08]', type=float)
    parser.add_option('--pulsar_peak_flux', '--psr_peak_flux', dest='pulsar_peak_flux', default=-1000, help='Pulsar peak flux density in Jy [default %default - negative means not specified]', type=float)
    parser.add_option('--pulsar_period', '--psr_period', dest='pulsar_period', default=0.2530651649482, help='Pulsar period in seconds [default %default - for B0950+08]', type=float)
    parser.add_option('--pulsar_pulse_width', '--psr_pulse_width', dest='pulsar_pulse_width', default=0.021, help='Pulsar pulse width in seconds [default %default - for B0950+08]', type=float)
    parser.add_option('--snr', '--show_snr', action="store_true", dest="show_snr", default=False, help="Show pulsar SNR [default %default]")

    # types :
    #   trcv_angelica_data_vs_time : Use T_rcv from lightcurve fits see RED curve in Ill.25 haslam_vs_angelica.odt for details
    #   trcv_angelica_data_vs_time_powerlawfit : Use T_rcv from lightcurve fit and fit of power law to T_rcv(freq) see RED curve in Ill.24 haslam_vs_angelica.odt for d
    #   trcv_haslam_data_vs_model  : Use T_rcv from data vs. model see GREEN in Ill.25 haslam_vs_angelica.odt for details
    #   trcv_from_skymodel_with_err : Use T_rcv as calculated with errors fitted with curve see eda_lightcurve_and_trcv.odt Ill. 13
    parser.add_option('--trcv_type', dest='trcv_type', default='trcv_from_skymodel_with_err',
                      help="Source of T_rcv possible values = value, lightcurve201612 (default), lightcurve_20160703_cubic, lightcurve_20160703_polfit, budi, data_vs_model_201612, trcv_angelica_data_vs_time, trcv_angelica_data_vs_time_powerlawfit, trcv_from_skymodel_with_err")
    #    parser.add_option('--trcv_type',dest='trcv_type',default='value',help="Source of T_rcv possible values = value, lightcurve201612 (default), lightcurve_20160703_cubic, lightcurve_20160703_polfit, budi, data_vs_model_201612, trcv_angelica_data_vs_time, trcv_angelica_data_vs_time_powerlawfit, trcv_from_skymodel_with_err")

    parser.add_option('--db', action="store_true", dest="use_db", default=False,
                      help="Use MWA database to get gridpoint of a given obsID ?")
    parser.add_option('--add_sources', action="store_true", dest="add_sources", default=False,
                      help="Overplot sources on the beam image")
    parser.add_option('-x', '--outsens_file', dest='out_sensitivity_file', default='eda_sensitivity',
                      help='Output filename for sensitivity')

    parser.add_option('-v', '--verbose', action="store_true", dest="verbose", default=False,
                      help="Increase verbosity of output")

    # parameters for sensitivity calculations :
    parser.add_option('-i', '--inttime', dest='inttime', default=120, type=float, help='Integration time to calculate sensitivity for [default % sec]')
    parser.add_option('--observation_duration','--total_observing_time', dest='total_observing_time', default=120, type=float, help='Total observing time in seconds [default % sec]')
    parser.add_option('--bandwidth', dest='bandwidth', default=1280000.00, type=float,
                      help='Bandwidth to calculate sensitivity for [default % Hz]')
    parser.add_option('-a', '--antnum', dest='antnum', default=128, type=int, help='Number of tiles [default %]')

    (options, args) = parser.parse_args()
    #  datetimestring = options.datetimestring
    
    print("DEBUG : here ???")
    if options.pointing_ra_deg is not None and options.pointing_dec_deg is not None :
       # optional imports
       from astropy.coordinates import SkyCoord, EarthLocation
       from astropy.time import Time
       print("INFO : converting from (RA,DEC) to (AZ,H) ...")
    
       uxtime = float(options.gps) + 315964783
       MWA_POS=EarthLocation.from_geodetic(lon="116:40:14.93",lat="-26:42:11.95",height=377.8)
       coord = SkyCoord( options.pointing_ra_deg, options.pointing_dec_deg, equinox='J2000',frame='icrs', unit='deg')
       coord.location = MWA_POS
       TimeCoord = Time( uxtime, scale='utc', format="unix" )
       coord.obstime = TimeCoord # Time( uxtime, scale='utc', format="unix" )
       altaz = coord.transform_to('altaz')
       az, alt = altaz.az.deg, altaz.alt.deg
       options.pointing_az_deg = az
       options.pointing_za_deg = (90 - alt)
       options.pointing_elev_deg = alt
       print("INFO : converted (RA,DEC) = (%.4f,%.4f) [deg] to (AZ,ZA) = (%.4f,%.4f) [deg] for uxtime = %.2f" % (options.pointing_ra_deg,options.pointing_dec_deg,options.pointing_az_deg,options.pointing_za_deg,uxtime))
    else :
       print("WARNNG : options.pointing_ra_deg or options.pointing_dec_deg not provided -> will use az,h")

    if options.pointing_elev_deg != 90:
        options.pointing_za_deg = 90 - options.pointing_elev_deg

    if options.dir is not None:
        mkdir_p(options.dir)

    if options.frequency is not None:
        if (',' in options.frequency):
            try:
                frequency = list(map(float, options.frequency.split(',')))
            except ValueError:
                logger.error("Could not parse frequency %s\n" % options.frequency)
                sys.exit(1)
        else:
            try:
                frequency = float(options.frequency)
            except ValueError:
                logger.error("Could not parse frequency %s\n" % options.frequency)
                sys.exit(1)
    else:
        frequency = options.frequency
    if options.channel is not None:
        if (',' in options.channel):
            try:
                channel = list(map(float, options.channel.split(',')))
            except ValueError:
                logger.error("Could not parse channel %s\n" % options.channel)
                sys.exit(1)
        else:
            try:
                channel = float(options.channel)
            except ValueError:
                logger.error("Could not parse channel %s\n" % options.channel)
                sys.exit(1)
    else:
        channel = options.channel

    if options.metafits is not None:
        try:
            f = pyfits.open(options.metafits)
        except Exception as e:
            logger.error('Unable to open FITS file %s: %s' % (options.metafits, e))
            sys.exit(1)
        if 'DELAYS' not in list(f[0].header.keys()):
            logger.error('Cannot find DELAYS in %s' % options.metafits)
            sys.exit(1)
        options.delays = f[0].header['DELAYS']
        try:
            # options.delays=[int(x) for x in options.delays.split(',')]
            print("delays from metafits file %s are %s" % (options.metafits, options.delays))
        except Exception as e:
            logger.error('Unable to parse beamformer delays %s: %s' % (options.delays, e))
            sys.exit(1)
            
            
        try :    
           if options.pointing_za_deg is None :
              alt = float( f[0].header['ALTITUDE'] )
              options.pointing_za_deg = 90.00 - alt
              print("DEBUG : ZA from metafits = %.8f [deg]" % (options.pointing_za_deg))
              
           if options.pointing_az_deg is None :
              options.pointing_az_deg = float( f[0].header['AZIMUTH'] )
              print("DEBUG : AZIMUTH from metafits = %.8f [deg]" % (options.pointing_az_deg))
           
                      
        except Exception as e:
           logger.warn('AZIMUTH or/and ALTITUDE keywords not found in metafits file %s -> ignored' % (options.metafits))

    if options.delays is not None:
        try:
            if (',' in options.delays):
                delays = list(map(int, options.delays.split(',')))
            else:
                delays = 16 * [int(options.delays)]
        except ValueError:
            logger.error("Could not parse beamformer delays %s\n" % options.delays)
            sys.exit(1)
    else:
        delays = options.delays

    if options.gps != 0:
        try:
            gps = int(options.gps)
        except ValueError:
            logger.error('Invalid gps parameter %s, must be integer seconds' % options.gps)
            sys.exit(1)
    else:
        if options.metafits is not None:
            logger.warning("Will try to use first 10 digits of the metafits file name %s" % options.metafits)
            try:
                gps = int(options.metafits[0:10])
            except ValueError:
                logger.error("Can't parse obsid from metafits file name: %s" % options.metafits)
                sys.exit(1)
        else:
            logger.error("gps seconds not passed as argument, and metafits file not specified, exiting.")
            sys.exit(1)

    extension = options.extension
    plottype = options.plottype
    model = options.model
    if model not in ['analytic', 'advanced', 'full_EE', 'full_EE_AAVS05', 'FEE', 'Full_EE', '2016', '2015', '2014']:
        logger.error("Model %s not found\n" % model)
        sys.exit(1)
    if plottype not in ['all', 'beam', 'sky', 'beamsky', 'beamsky_scaled', 'None']:
        logger.error("Plot type %s not found\n" % plottype)
        sys.exit(1)

    print("########################################")
    print("PARAMETERS :")
    print("########################################")
    print("gridpoint  = %d" % (options.gridpoint))
    print("use db     = %s" % (options.use_db))
    print("T_rcv type = %s" % (options.trcv_type))
    print("Incoherent sum = %s" % (options.incoherent))
    print("N bins     = %d" % (options.n_phase_bins))
    print("Pulsar observing time = %.3f [sec]" % (options.pulsar_observing_time))
    print("Pulsar peak flux = %.6f [Jy]" % (options.pulsar_peak_flux))
    print("Total observing time = %.2f [sec]" % (options.total_observing_time))
    print("########################################")

    #    if (datetimestring is None):
    #        if (datestring is not None and timestring is not None):
    #            datetimestring=datestring.replace('-','') + timestring.replace(':','')
    #    if gpsstring is not None:
    #        try:
    #            mjd,ut=ephem_utils.calcUTGPSseconds(int(gpsstring))
    #        except:
    #            logger.error('Cannot convert gpsstring %s to a date/time' % gpsstring)
    #            sys.exit(1)
    #        yr,mn,dy=ephem_utils.mjd_cal(mjd)
    #        datetimestring=('%04d%02d%02d' % (yr,mn,dy))+ ephem_utils.dec2sexstring(ut,digits=0,roundseconds=1).replace(':','')
    #    if (datetimestring is None):
    #        logger.error("Must supply a date/time\n")
    #        sys.exit(1)
    #    if len(datetimestring) != 14:
    #        logger.error('Format of date/time is YYYYMMDDhhmmss; %s is not valid\n' % datetimestring)
    #        sys.exit(1)

    gridpoint = -1
    if options.use_db:
        if options.gps > 0:
            print("INFO : Reading information from MWA metadata web service ...")
            obs = metadata.get_observation(obsid=options.gps)
            delays = obs['rfstreams']['0']['delays']
            gridpoint = obs['metadata']['gridpoint_number']
    else:
        if options.gridpoint >= 0:
            gridpoint = options.gridpoint
            delays_xy = mwa_sweet_spots.get_delays(gridpoint)
            delays = delays_xy[0]
            
            if options.pointing_za_deg is None and options.pointing_az_deg is None :
               options.pointing_za_deg = mwa_sweet_spots.all_grid_points[gridpoint][3]
               options.pointing_elev_deg = mwa_sweet_spots.all_grid_points[gridpoint][2]
               options.pointing_az_deg = mwa_sweet_spots.all_grid_points[gridpoint][1]
               
               print("WARNING : parameters --pointing_za_deg and --pointing_az_deg not specified -> using center of the beam at (az,za,elev) = (%.6f,%.6f,%.6f) [deg]" % (options.pointing_az_deg,options.pointing_za_deg,options.pointing_elev_deg))
               
            
        print("Using of MWA database is not required")

    print("Pointing information for obsid=%d" % (int(options.gps)))
    print("gridpoint = %d" % (gridpoint))
    print("delays    = %s" % (delays))
    print("Pointing direction to source = (az,za) = (%.8f,%.8f) [deg]" % (options.pointing_az_deg,
                                                                          options.pointing_za_deg))
    print("T_rcv     = %.2f K" % (options.t_rcv))

    if (len(delays) < 16):
        logger.error("Must supply 1 or 16 delays\n")
        sys.exit(1)
    if (frequency is None):
        if (channel is not None):
            if (isinstance(channel, list)):
                frequency = list(1.28 * np.array(channel))  # multiplication by 1e6 is done later at line Convert to Hz
            else:
                frequency = 1.28 * channel  # multiplication by 1e6 is done later at line Convert to Hz
    if frequency is None:
        logger.error("Must supply frequency or channel\n")
        sys.exit(1)
    if (isinstance(frequency, int) or isinstance(frequency, float)):
        frequency = [frequency]
    frequency = np.array(frequency) * 1e6  # Convert to Hz

    outfile_sens_XX = options.out_sensitivity_file + "_XX.txt"
    outfile_sens_YY = options.out_sensitivity_file + "_YY.txt"
    f_out_XX = open(outfile_sens_XX, "w")
    f_out_YY = open(outfile_sens_YY, "w")
    
    f_out_XX.write("# FREQ[MHz] A/T[m^2/K] T_sys[K] A_eff[m^2] T_rcv[K] Image_Noise[Jy] Beam\n")
    f_out_YY.write("# FREQ[MHz] A/T[m^2/K] T_sys[K] A_eff[m^2] T_rcv[K] Image_Noise[Jy] Beam\n")

    # receiver temperature :
    T_rcv = options.t_rcv

    noise_x_total = 0
    noise_y_total = 0
    noise_i_total2 = 0
    noise_count   = 0
    
    noise_x_weighted = 0
    noise_y_weighted = 0
    noise_i_weighted = 0
    beam_i_sum = 0

    gps_start = int(options.gps)
    gps= int( options.gps )
    while gps < ( gps_start + options.total_observing_time) :
       print("DEBUG : calculating sensitivity at GPS TIME = %d" % (gps))
    
       for freq in frequency:
           # ef calculate_sensitivity( freq, delays, trcv_type, T_rcv, size, dir, pointing_az_deg=0, pointing_za_deg=0, add_source=False, zenithnorm=True, antnum=128, inttime=120,  bandwidth=1280000 ) :
           # (T_sys_XX,sens_XX,sefd_XX,noise_XX,T_sys_YY,sens_YY,sefd_YY,noise_YY)
           freq_mhz = freq / 1e6
           (aeff_XX, T_sys_XX, sens_XX, sefd_XX, noise_XX, beam_XX, aeff_YY, T_sys_YY, sens_YY, sefd_YY,
            noise_YY, beam_YY) = calculate_sensitivity( options, freq, delays, gps, options.trcv_type, T_rcv, options.size, options.dir,
                                              model=model,
                                              plottype=plottype,
                                              extension=extension,
                                              pointing_az_deg=options.pointing_az_deg,
                                              pointing_za_deg=options.pointing_za_deg,
                                              add_sources=options.add_sources,
                                              zenithnorm=options.zenithnorm,
                                              antnum=options.antnum,
                                              inttime=options.inttime,
                                              bandwidth=options.bandwidth )

           out_line_XX = "%.8f %.8f %.2f %.8f %.8f %.8f\n" % (freq_mhz, sens_XX, T_sys_XX, aeff_XX, T_rcv, noise_XX)
           out_line_YY = "%.8f %.8f %.2f %.8f %.8f %.8f\n" % (freq_mhz, sens_YY, T_sys_YY, aeff_YY, T_rcv, noise_YY)
           f_out_XX.write(out_line_XX)
           f_out_YY.write(out_line_YY)
           
           noise_I = 0.5*math.sqrt( noise_XX*noise_XX + noise_YY*noise_YY )
           beam_i = (beam_XX + beam_YY)/2.00
           noise_x_total += (noise_XX*noise_XX)
           noise_y_total += (noise_YY*noise_YY)
           noise_i_total2 += (noise_I*noise_I)
           noise_x_weighted += (noise_XX*beam_i)*(noise_XX*beam_i)
           noise_y_weighted += (noise_YY*beam_i)*(noise_XX*beam_i)
           noise_i_weighted += (noise_I*beam_i)*(noise_I*beam_i)
           beam_i_sum += (beam_i*beam_i)
           noise_count   += 1
           
       gps += options.inttime
       print("DEBUG : gps = %d (added %.2f sec)" % (gps,options.inttime))

    f_out_XX.close()
    f_out_YY.close()

    noise_x_total = math.sqrt( noise_x_total ) / noise_count
    noise_y_total = math.sqrt( noise_y_total ) / noise_count
    noise_i_total = 0.5*math.sqrt( noise_x_total*noise_x_total + noise_y_total*noise_y_total )
    noise_i_total2 = math.sqrt( noise_i_total2 ) / noise_count
    print("Noise expected in %d [sec] image is" % (options.total_observing_time))
    print("\t X pol. RMS_x = %.6f [Jy]" % (noise_x_total))
    print("\t Y pol. RMS_y = %.6f [Jy]" % (noise_y_total))
    print("\t Stokes I pol. RMS_stokes_i = %.6f [Jy] (vs. other way %.6f [Jy])" % (noise_i_total,noise_i_total2))
    
    noise_x_weighted = noise_x_weighted / beam_i_sum
    noise_y_weighted = noise_y_weighted / beam_i_sum
    noise_i_weighted = noise_i_weighted / beam_i_sum
    print("Noise weighted by the beam (as in SMART averaging procedure):")
    print("\t X pol. RMS_x_weighted = %.6f [Jy]" % (noise_x_weighted))
    print("\t Y pol. RMS_y_weighted = %.6f [Jy]" % (noise_y_weighted))
    print("\t Stokes I pol. RMS_stokes_i_weighted = %.6f [Jy]" % (noise_i_weighted))


if __name__ == "__main__":
    main()

# TODO :
# - lacks dOMEGA !!!  what is this here - that's why it is too low !!!
