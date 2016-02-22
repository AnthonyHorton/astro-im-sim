# This is Python 3 code but with these imports there's at least a chance it'll work in Python 2
from __future__ import division, print_function, unicode_literals, absolute_import, with_statement

import numpy as np
from scipy.interpolate import RectSphereBivariateSpline, SmoothBivariateSpline, InterpolatedUnivariateSpline
import astropy.io.fits as fits
import astropy.units as u
from astropy.coordinates import SkyCoord, GeocentricTrueEcliptic, get_sun, Angle
from astropy.time import Time
from astropy.wcs import WCS

class ZodiacalLight:
    """
    Class representing the Zodiacal Light sky background. Includes methods that return
    the absolute surface brightness spectral flux density at the ecliptic poles as
    well as the relative brightness variations as a function of position on the sky.
    """
    # Parameters for the zodiacal light spectrum

    # Colina, Bohlin & Castelli solar spectrum is normalised to V band flux 
    # of 184.2 ergs/s/cm^2/A,
    solar_normalisation = 184.2 * u.erg * u.second**-1 * u.cm**-2 * u.Angstrom**-1
    # Leinert at al NEP zodical light 1.81e-18 erg/s/cm^2/A/arcsec^2 at 0.5 um, 
    # Aldering suggests using 0.01 dex lower.
    zl_nep = 1.81e-18 * u.erg * u.second**-1 * u.cm**-2 * u.Angstrom**-1 * \
             u.arcsecond**-2 * 10**(-0.01)
    zl_normalisation = zl_nep / solar_normalisation
    # Central wavelength for reddening/normalisation
    lambda_c = 0.5 * u.micron
    # Aldering reddening parameters
    f_blue = 0.9
    f_red = 0.48

    # Parameters for the zodical light spatial dependence

    # Data from table 17, Leinert et al (1997).
    llsun = np.array([0, 5 ,10, 15, 20, 25, 30, 35, 40, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180])
    beta = np.array([0, 5, 10, 15, 20, 25, 30, 45, 60, 75])
    zl_scale = np.array([[np.NaN, np.NaN, np.NaN, 3140, 1610, 985, 640, 275, 150, 100], \
                         [np.NaN, np.NaN, np.NaN, 2940, 1540, 945, 625, 271, 150, 100], \
                         [np.NaN, np.NaN, 4740, 2470, 1370, 865, 590, 264, 148, 100], \
                         [11500, 6780, 3440, 1860, 1110, 755, 525, 251, 146, 100], \
                         [6400, 4480, 2410, 1410, 910, 635, 454, 237, 141, 99], \
                         [3840, 2830, 1730, 1100, 749, 545, 410, 223, 136, 97], \
                         [2480, 1870, 1220, 845, 615, 467, 365, 207, 131, 95], \
                         [1650, 1270, 910, 680, 510, 397, 320, 193, 125, 93], \
                         [1180, 940, 700, 530, 416, 338, 282, 179, 120, 92], \
                         [910, 730, 555, 442, 356, 292, 250, 166, 116, 90], \
                         [505, 442, 352, 292, 243, 209, 183, 134, 104, 86], \
                         [338, 317, 269, 227, 196, 172, 151, 116, 93, 82], \
                         [259, 251, 225, 193, 166, 147, 132, 104, 86, 79], \
                         [212, 210, 197, 170, 150, 133, 119, 96, 82, 77], \
                         [188, 186, 177, 154, 138, 125, 113, 90, 77, 74], \
                         [179, 178, 166, 147, 134, 122, 110, 90, 77, 73], \
                         [179, 178, 165, 148, 137, 127, 116, 96, 79, 72], \
                         [196, 192, 179, 165, 151, 141, 131, 104, 82, 72], \
                         [230, 212, 195, 178, 163, 148, 134, 105, 83, 72]]).transpose()


    def __init__(self, solar_path='../resources/sun_castelli.fits'):
        # Pre-calculate zodiacal light spectrum for later use.
        self._calculate_spectrum(solar_path)
        self._calculate_spatial()

    def _calculate_spectrum(self, solar_path):
        """
        Pre-calculates absolute surface brightness spectral flux density
        of the Zodiacal Light at the ecliptic poles.
        """
        # Load absolute solar spectrum from Collina, Bohlin & Castelli (1996)
        sun = fits.open(solar_path)
        sun_waves = sun[1].data['WAVELENGTH'] * u.Angstrom 
        # sfd = spectral flux density
        sun_sfd = sun[1].data['FLUX'] * u.erg * u.second**-1 * u.cm**-2 * u.Angstrom**-1

        self.waves = sun_waves.to(u.micron)
        
        # Covert to zodiacal light spectrym by following the normalisation and reddening
        # prescription of Leinert et al (1997) with the revised parameters from 
        # Aldering (2001), as used in the HST ETC (Giavalsico, Sahi, Bohlin (2202)).
        
        # Reddening factor
        rfactor = np.where(sun_waves < ZodiacalLight.lambda_c, \
                           1.0 + ZodiacalLight.f_blue * np.log(sun_waves/ZodiacalLight.lambda_c), \
                           1.0 + ZodiacalLight.f_red * np.log(sun_waves/ZodiacalLight.lambda_c))
        # Apply normalisation and reddening
        sfd = sun_sfd * ZodiacalLight.zl_normalisation * rfactor
        # #DownWithErgs
        self.sfd = sfd.to(u.Watt * u.m**-2 * u.arcsecond**-2 * u.micron**-1)
        # Also calculate in photon spectral flux density units. Fudge needed because equivalencies
        # don't currently include surface brightness units.
        fudge = sfd * u.arcsecond**2
        fudge = fudge.to(u.photon * u.second**-1 * u.m**-2 *  u.micron**-1, equivalencies=u.spectral_density(self.waves))
        self.photon_sfd = fudge / u.arcsecond**2

    def _calculate_spatial(self):
        """
        Pre-calculate the relative Zodiacal Light brightness variation with sky position
        """
        # Normalise scaling factor to a value of 1.0 at the NEP
        zl_scale = ZodiacalLight.zl_scale / 77

        # Expand range of angles to cover the full sphere by using symmetry
        beta = np.array(np.concatenate((-np.flipud(ZodiacalLight.beta)[:-1], ZodiacalLight.beta))) * u.degree
        llsun = np.array(np.concatenate((ZodiacalLight.llsun, 360 - np.flipud(ZodiacalLight.llsun)[1:-1]))) * u.degree
        zl_scale = np.concatenate((np.flipud(zl_scale)[:-1],zl_scale))
        zl_scale = np.concatenate((zl_scale,np.fliplr(zl_scale)[:,1:-1]),axis=1)

        # Convert angles to radians within the required ranges.
        beta = beta.to(u.radian).value + np.pi/2
        llsun = llsun.to(u.radian).value
        # For initial cartesian interpolation want the hole in the middle of the data,
        # i.e. want to remap longitudes onto -180 to 180, not 0 to 360 degrees.
        # Only want the region of closely spaced data point near to the Sun.
        beta_c = beta[3:-3]
        nl = len(llsun)
        llsun_c = np.concatenate((llsun[nl//2+9:]-2*np.pi,llsun[:nl//2-8]))
        zl_scale_c = np.concatenate((zl_scale[3:-3,nl//2+9:],zl_scale[3:-3,:nl//2-8]),axis=1)

        # Convert everthing to 1D arrays (lists) of x, y and z coordinates.
        llsuns, betas = np.meshgrid(llsun_c, beta_c)
        llsuns_c = llsuns.ravel()
        betas_c = betas.ravel()
        zl_scale_cflat = zl_scale_c.ravel()

        # Indices of the non-NaN points
        good = np.where(np.isfinite(zl_scale_cflat))

        # 2D cartesian interpolation function
        zl_scale_c_interp = SmoothBivariateSpline(betas_c[good], llsuns_c[good], zl_scale_cflat[good])

        # Calculate interpolated values
        zl_scale_fill = zl_scale_c_interp(beta_c, llsun_c)

        # Remap the interpolated values back to original ranges of coordinates
        zl_patch = np.zeros(zl_scale.shape)
        zl_patch[3:16,0:10] = zl_scale_fill[:,9:]
        zl_patch[3:16,-9:] = zl_scale_fill[:,:9]

        # Fill the hole in the original data with values from the cartesian interpolation
        zl_patched = np.where(np.isfinite(zl_scale),zl_scale,zl_patch)

        # Spherical interpolation function from the full, filled data set
        self._spatial = RectSphereBivariateSpline(beta, llsun, zl_patched, \
                                                  pole_continuity=(False,False), pole_values=(1.0, 1.0), \
                                                  pole_exact=True, pole_flat=False)
        
    def relative_brightness(self, position, time):
        """
        Calculate the Zodiacal Light surface brightness relative to that at
        the ecliptic poles for a given sky position and observing time.

        Arguments:

        position - sky position(s) in the form of either an astropy.coordinates.SkyCoord
                   object or a string that can be converted into one.
        time -     time of observation in the form of either an astropy.time.Time
                   or a string that can be converted into one.
        
        Returns:

        rel_SB -   relative sky brightness of the Zodiacal light 
        """
        # Convert position(s) to SkyCoord if not already one
        if not isinstance(position, SkyCoord):
            position = SkyCoord(position)

        # Convert time to a Time if not already one
        if not isinstance(time, Time):
            time = Time(time)

        # Convert to ecliptic coordinates at current epoch
        position = position.transform_to(GeocentricTrueEcliptic(equinox=time))

        # Get position of the Sun
        sun = get_sun(time).transform_to(GeocentricTrueEcliptic(equinox=time))
        
        # Ecliptic latitude, remapped to range 0 to 180 degrees, in radians
        beta = (Angle(90 * u.degree) - position.lat).radian
        # Ecliptic longitude minus Sun's ecliptic longitude, remapped to 
        # range 0 to 360 degrees, in radians
        llsun = (position.lon - sun.lon).wrap_at(360 * u.degree).radian

        return self._spatial(beta, llsun, grid=False)

class Imager:
    """
    Class representing an imaging instrument.
    """
    def __init__(self, npix_x, npix_y, pixel_scale):
        """
        Constructs a simple template WCS to store the focal plane configuration parameters
        """
        self.wcs = WCS(naxis=2)
        self.wcs._naxis1 = npix_x
        self.wcs._naxis2 = npix_y
        self.wcs.wcs.crpix = [(npix_x + 1)/2, (npix_y + 1)/2]
        self.wcs.wcs.cdelt = [pixel_scale.to(u.degree).value, pixel_scale.to(u.degree).value]
        self.wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']

    def get_pixel_coords(self, centre):
        """
        Utility function to return a SkyCoord array containing the on sky position
        of the centre of all the pixels in the image centre, given a SkyCoord for
        the field centre
        """
        # Ensure centre is a SkyCoord (this allows entering centre as a string)
        if not isinstance(centre, SkyCoord):
            centre = SkyCoord(centre)

        # Set field centre coordinates in internal WCS
        self.wcs.wcs.crval = [centre.icrs.ra.value, centre.icrs.dec.value]

        # Arrays of pixel coordinates
        XY = np.meshgrid(np.arange(self.wcs._naxis1), np.arange(self.wcs._naxis2))
        
        # Convert to arrays of RA, dec (ICRS, decimal degrees)
        RAdec = self.wcs.all_pix2world(XY[0], XY[1], 0)

        return RAdec
