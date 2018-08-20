.. ThinGreyscale documentation master file, created by
   sphinx-quickstart on Sun Feb 12 17:11:03 2012.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to ThinGreyscale's documentation!
============================================

ThinGreyScale is a QGIS plugin.

.. toctree::
   :maxdepth: 2

.. contents::

Functionality
==============

Performs thinning of a greyscale image (or an image band) using a
slightly modified version of an algorithm presented by Biagioni and
Eriksson [1].

Based on a user specified set of levels, the image (or band)
is thinned to a skeleton by first thinning the set of pixels that
have values higher than or equal to the highest level.
Then the next highest level is considered.
Here all pixels that have values in the two highest levels are
considered, but the thinning is constrained by the skeleton from
the highest level.
This continues until the lowest level is reached.

The result is a skeleton raster with skeleton pixels that have
values corresonding to the level at which they were found.
The lowest level has value 1.
The skeleton raster is saved as GeoTIFF, either at a location
specified by the user or in the user's tempdir (files are not
deleted automatically).

It is assumed that the higher the pixel values in the input image is,
the more "important" is the pixel.

The greyscale skeleton can be vectorised with GRASS *r.to.vect* by
first binarising it (choosing an appropriate threshold), and then
thinning it using GRASS *r.thin* to get a skeleton that is
compatible with *r.to.vect*.

Limitations
=============

* A maximum of 255 levels can be used.

* Large images may cause memory problems and very long execution
  times.
  64 bit Python is recommended.
  In order to limit execution times, the lowest level should not
  include a high percentage of the total number of pixels in the
  image.

The algorithm
=================

The algorithm was proposed by Biagioni and Eriksson [1], using the
notation of Zhang and Suen [2].
We had to slightly modify the original algorithm due to some problems
with its behaviour.

The input to the algorithm is a greyscale image and a set of levels,
ordered on increasing value.
At each level, the thinning is performed on a combination of the
skeleton from the higher level and a binary image containing 1's
for all pixels that have values larger then the current level:

S\ :sub:`i` = Thin(S\ :sub:`i+1` + T\ :sub:`i`)

S\ :sub:`i` is the skeleton image for level i, while T\ :sub:`i` is
the threshold image for level i.

At each level the Thin algorithm runs as follows:

.. code-block:: python

    # Skeletonize
    # Zhang & Suen 1984: Parallel processing - each pixel
    #   is considered based on the values from the previous
    #   step

    # Notation and explanations:
    #
    # Naming of the neighbouring pixels:
    # P9 P2 P3
    # P8 P1 P4
    # P7 P6 P5
    #
    # B(P1): number of non-zero neighbours of P1
    # A(P1): number of (0,>=1) pairs in the ordered set
    #        P2,P3,...,P9,P2 (avoids removing "nodes"?)

    # Step 1:
    Repeat until convergence:
        # Substep 1:
        for all pixels:
            set P1 = 0 if all of the following conditions hold:
                B(P1) >= 2;     # pixels with one or two non-zero neigbours will not be affected
                B(P1) <= 6;     # pixels with seven or eight non-zero neighbours will not be affected
                A(P1) = 1;      # "nodes" (where more than two "lines" meet) will not be removed
                # P2 x P4 x P6 != 1;  # paper original, but does not work
                # P4 x P6 x P8 != 1;  # paper original, but does not work
                P2 x P4 x P6 = 0;  
                P4 x P6 x P8 = 0;

        # Substep 2:
        for all pixels:
            set P1 = 0 if all of the following conditions hold:
                B(P1) >= 2;
                B(P1) <= 6;
                A(P1) = 1;
                # P2 x P4 x P8 != 1; # paper original - does not work
                # P2 x P6 x P8 != 1; # paper original - does not work
                P2 x P4 x P8 = 0;
                P2 x P6 x P8 = 0;

    # Step 2:
    # deletes completely contained pixels (and some cul-de-sac pixels)
    # Could break bridges (if the illustrated situation occurs):
    # ******
    #   **
    # ******
    for all pixels:
        set P1 = 0 if the following condition holds:
            B>=7)
                    
The result is not a pure skeleton, as there are some pixels that have
more than two 9-neighbours even if they are not "nodes".
The following situation may result (because of the A(P1)=1 condition):

.. code-block:: python

    ##
     ####
    

Options
==========

* Input raster layer.

* Band of the input raster layer.
  If the raster image consists of more than one band, the band to
  use for thinning can be specified.

* Minimum value for the skeleton algorithm (lower bound for the
  minimum level).
  The default is the mean value of the input layer band, but this
  can easily be changed.
  For integer input raster layers, the mean value is rounded up to
  the closest integer.

* Maximum value for the skeleton algorithm (upper bound for the
  highest level).
  The default is the maximum value of the input layer band.
  Setting the maximum value so something that is less than the raster
  layer maximum is normally not a good idea.

* The levels to be used by the algorithm can be modified by setting
  the level boundaries manuall using the *add* and *remove* buttons,
  or the levels can be suggested using the *Suggest levels* button
  (based on the   minimum and maximum values and the number of
  levels, using equal intervals).

* Output raster dataset file name and location.
  If no output file name is specified, a GeoTIFF file with prefix
  "greyskel" will be created in the user's tempdir.

* The *Use level values as output pixel values* can be used to
  output the lower boundary value of the level instead of the level
  sequence number (1 for the lowest level).

* The histogram of input raster values can be generated.
  The generated histogram will include the values between the minimum
  value and the maximum value.

References
===========

[1] Biagioni and Eriksson: *Map Inference in the Face of Noise and Disparity*.  SIGSPATIAL GIS, pages 79-88. ACM, 2012.

[2] Zhang & Suen 1984: *A fast parallel algorithm for thinning digital patterns*.  Communications of the ACM, volume 27, issue 3, pages 236-239. ACM, 1984.

Links
======
`ThinGreyscale Plugin`_

`ThinGreyscale code repository`_

`ThinGreyscale issues`_

Citation
==========

Would you like to cite / reference this plugin?

Tveite, H. (2015). The QGIS Thin Greyscale Image to Skeleton Plugin. http://plugins.qgis.org/plugins/ThinGreyscale/.

Bibtex:

.. code-block:: latex

  @misc{tveitesde,
    author =   {Håvard Tveite},
    title =    {The {QGIS} Thin Greyscale Image to Skeleton Plugin},
    howpublished = {\url{http://plugins.qgis.org/plugins/ThinGreyscale/}},
    year = {2015--2018}
  }


.. _ThinGreyscale code repository: https://github.com/havatv/qgisthingreyscaleplugin.git
.. _ThinGreyscale Plugin: http://arken.umb.no/~havatv/gis/qgisplugins/SDEllipse
.. _ThinGreyscale issues: https://github.com/havatv/qgisthingreyscaleplugin/issues

