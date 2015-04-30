# -*- coding: utf-8 -*-
"""
/***************************************************************************
     ThinGreyScaleEngine
                             -------------------
        begin                : 2014-09-04
        git sha              : $Format:%H$
        copyright            : (C) 2014 by Håvard Tveite
        email                : havard.tveite@nmbu.no
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from math import pow, trunc, log
import numpy as np
# Should sparse matrices be used instead (scipy.sparse)?
#import scipy as scp
from PyQt4.QtCore import QCoreApplication, QObject, pyqtSignal
from PyQt4.QtCore import QPointF, QLineF, QRectF, QPoint


class Worker(QObject):
    '''The worker that does the heavy lifting.
    /*
     *  Does the thinning of the grayscale raster.
     *  Biagioni and Eriksson: "Map Inference in the Face of Noise
     *    and Disparity", SIGSPATIAL GIS, pages 79-88. ACM, 2012
    */
    '''
    maxlevels = 255  # we use uint8 to store the skeleton!
    # Define the signals used to communicate back to the application
    progress = pyqtSignal(float)  # For reporting progress
    status = pyqtSignal(str)      # For reporting status
    error = pyqtSignal(str)       # For reporting errors
    #killed = pyqtSignal()
    # Signal for sending over the result:
    finished = pyqtSignal(bool, object)

    def __init__(self, inputlayer, levels, intvalues):
        """Initialise.

        Arguments:
        inputlayer -- (QgsRasterLayer) The input raster layer (greyscale)
        levels -- vector of numbers
        intvalues -- (boolean)
        """

        QObject.__init__(self)  # Essential!
        # Creating instance variables from the parameters
        self.inpl = inputlayer
        self.inputrdp = self.inpl.dataProvider()
        self.inputextent = self.inpl.extent()
        self.levels = levels
        self.minrastervalue = self.levels[0]
        self.maxrastervalue = self.levels[len(self.levels) - 1]
        self.levels.pop()
        self.intvalues = intvalues
        #self.intvalues = True # while testing !!!???
        # Creating instance variables for the progress bar ++
        # Number of elements that have been processed - updated by
        # calculate_progress
        self.processed = 0
        self.levelsprocessed = 0
        # Current percentage of progress - updated by
        # calculate_progress
        self.percentage = 0
        self.levelspercentage = 0
        # Flag set by kill(), checked in the loop
        self.abort = False
        # Number of features in the input layer - used by
        # calculate_progress
        self.numberofrows = self.inpl.height()
        self.numberoflevels = len(self.levels)
        #self.numberofrows = 10000
        # The number of elements that is needed to increment the
        # progressbar - set early in run()
        self.increment = self.numberofrows // 1000
        self.levelincrement = 1

    def run(self):
        try:
            #gdal.AllRegister()
            # Open the input raster file
            # register the gdal drivers
            # Open and assign the contents of the raster file to a dataset
            #dataset = gdal.Open(self.inpl, GA_ReadOnly)
            width = self.inpl.width()
            height = self.inpl.height()
            extwidth = self.inputextent.width()
            extheight = self.inputextent.height()
            #rastercount = numpy.empty(dataset.RasterCount)
            self.status.emit('Starting - raster: ' + str(width) + ','
                             + str(height) + ' intvalues: ' +
                             str(self.intvalues))

            # Read the raster block and get the maximum value
            #self.maxvalue = 0
            rasterblock = self.inputrdp.block(1, self.inputextent,
                                              width, height)
            # Create a numpy array version of the image
            if self.intvalues:
                imageMat = np.zeros((height, width), dtype=np.uint8)
            else:
                imageMat = np.zeros((height, width), dtype=np.float16)
            # This one takes a lot of time!
            for row in range(height):
                if self.abort is True:
                    break
                for column in range(width):
                    if self.abort is True:
                        break
                    if self.intvalues:
                        imageMat[row, column] = int(rasterblock.value(
                                                   row, column))  # ??
                    else:
                        imageMat[row, column] = rasterblock.value(
                                                         row, column)
                    #if rasterblock.value(row,column) > self.maxvalue:
                    #    self.maxvalue = rasterblock.value(row,column)
            #self.maxvalue = np.amax(imageMat)
            # Determine the levels (powers of two)
            #maxlevel = int(trunc(log(self.maxvalue,2)))
            #levels = []
            #for i in range(0,maxlevel+1):
            #    levels.append(int(round(pow(2,i))))
            #self.status.emit('Levels ' + str(levels))

            # Remove the values that are greater than the maximium value
            # or smaller than the minimum value
            #imageMat = imageMat[(imageMat <= self.maxrastervalue) |
            #                      (imageMat >= self.minrastervalue)]
            # Check if there are too many levels
            if len(self.levels) > self.maxlevels:
                self.status.emit('Too many levels - only ' +
                                 str(self.maxlevels) +
                                 ' levels supported - truncating!')
                del self.levels[self.maxlevels:]
            # List for storing matrices from all the steps
            #SkelMatrices = []
            # Initialise the skeleton raster as a matrix of boolean
            # Add an "edge" around the image to protect the filter
            #SkelMat = np.zeros((height + 2, width + 2), dtype=np.int16)
            SkelMat = np.zeros((height + 2, width + 2), dtype=np.uint8)

            # Go through the levels (start at the top)
            for level in reversed(self.levels):
                if level < self.minrastervalue:
                    break
                self.status.emit('Entering level ' + str(level))
                if self.abort is True:
                    break
                # Create the binary image (T) for this level
                # Add an "edge" around the image to protect the filter
                ThresMat = np.zeros((height + 2, width + 2), dtype=np.bool)
                relevantpixels = np.where((imageMat >= level) &
                                   (imageMat <= self.maxrastervalue))
                checkpixels = zip(relevantpixels[0], relevantpixels[1])
                for (row, column) in checkpixels:
                    if self.abort is True:
                        break
                    ThresMat[row + 1, column + 1] = True
                self.status.emit('Threshold matrix created - sum: ' +
                                               str(np.sum(ThresMat)))
                # Prepare the matrix for skeletonisation
                # S_l = skeletonize(T_l + S_(l+1))
                #SkelMat = ThresMat + SkelMat
                SkelMat = np.add(ThresMat, SkelMat)
                #   For some reason the result is not a pure skeleton,
                #   as there are some extra pixels for diagonals.
                # Skeletonize
                # Zhang & Suen 1984: Parallel processing - each pixel
                #   is considered based on the values from the previous
                #   step
                # Naming of the neighbouring pixels:
                # P9 P2 P3
                # P8 P1 P4
                # P7 P6 P5
                # B(P1): number of non-zero neighbours of P1
                # A(P1): number of (0,>=1) pairs in the ordered set
                #        P2,P3,...,P9,P2 (avoids removing "nodes"?)
                # Repeat the thinning algorithm until it converges
                changes = True
                #numChanges = 0
                iterations = 0
                # Step 1
                while changes:
                    if self.abort is True:
                        break
                    changes = False
                    iterations = iterations + 1
                    #self.processed = 0
                    #self.percentage = 0
                    # Substep 1: P1 = 0 if B(P1) >= 2; B(P1) <= 6; A(P1) = 1;
                    #    P2 x P4 x P6 != 1; P4 x P6 x P8 != 1;
                    #    # that did not work, so used the following instead
                    #    P2 x P4 x P6 = 0; P4 x P6 x P8 = 0;
                    #nextbinary = np.zeros((height,width), dtype=bool)
                    #newSkelMat = np.zeros((height+2,width+2), dtype=np.int16)
                    #newSkelMat = np.zeros((height+2,width+2), dtype=np.uint8)
                    newSkelMat = np.array(SkelMat, dtype=np.uint8)
                    # Use np.nonzero(SkelMat) instead of double for-loop?

                    relevantpixels = np.where(SkelMat == 1)
                    checkpixels = zip(relevantpixels[0], relevantpixels[1])
                    for (row, column) in checkpixels:
                        if self.abort is True:
                            break
                        B = 0
                        A = 0
                        #P1 = SkelMat[row,column]
                        P2 = SkelMat[row - 1, column]
                        P3 = SkelMat[row - 1, column + 1]
                        P4 = SkelMat[row, column + 1]
                        P5 = SkelMat[row + 1, column + 1]
                        P6 = SkelMat[row + 1, column]
                        P7 = SkelMat[row + 1, column - 1]
                        P8 = SkelMat[row, column - 1]
                        P9 = SkelMat[row - 1, column - 1]
                        if P2 > 0:
                            B = B + 1
                            if P9 == 0:
                                A = A + 1
                        if P3 > 0:
                            B = B + 1
                            if P2 == 0:
                                A = A + 1
                        if P4 > 0:
                            B = B + 1
                            if P3 == 0:
                                A = A + 1
                        if P5 > 0:
                            B = B + 1
                            if P4 == 0:
                                A = A + 1
                        if P6 > 0:
                            B = B + 1
                            if P5 == 0:
                                A = A + 1
                        if P7 > 0:
                            B = B + 1
                            if P6 == 0:
                                A = A + 1
                        if P8 > 0:
                            B = B + 1
                            if P7 == 0:
                                A = A + 1
                        if P9 > 0:
                            B = B + 1
                            if P8 == 0:
                                A = A + 1
                        tozero = (B >= 2 and B <= 6 and A == 1 and
                                      (P2 == 0 or P4 == 0 or P6 == 0) and
                                      (P4 == 0 or P6 == 0 or P8 == 0))
#                                      (P2 == 0 or P4 == 0 or P6 == 0 or
#                                       P2 > 1 or P4 > 1 or P6 > 1) and
#                                      (P4 == 0 or P6 == 0 or P8 == 0 or
#                                       P4 > 0 or P6 > 0 or P8 > 0))
##                                     (P2 * P4 * P6 == 0) and
##                                     (P4 * P6 * P8 == 0))
###                                      (P2 * P4 * P6 != 1) and
###                                     (P4 * P6 * P8 != 1))
                        if tozero:
                            #numChanges = numChanges + 1
                            changes = True
                            newSkelMat[row, column] = 0
                        #else:
                        #    self.status.emit('Matrix -: ' + str(P1) +
                        #        str(P2) + str(P3) + str(P4) + str(P5) +
                        #        str(P6) + str(P7) + str(P8) + str(P9) +
                        #        ' ' + str(B) + ' ' + str(A) + ' ' +
                        #        str(P2 * P4 * P6) + ' ' +
                        #        str(P4 * P6 * P8) + '(' + str(row) +
                        #        ',' + str(column) + ')')
                        #self.calculate_progress()
                    self.status.emit('1a')
                    # Substep 2: P1 = 0 if B(P1) >= 2; B(P1) <= 6; A(P1) = 1;
                    #    P2 x P4 x P8 != 1; P2 x P6 x P8 != 1
                    SkelMat = newSkelMat
                    newSkelMat = np.array(SkelMat, dtype=np.uint8)
                    #newSkelMat = np.zeros((height + 2, width + 2),
                    #                                dtype=np.int16)
                    #newSkelMat = np.zeros((height + 2, width + 2),
                    #                                dtype=np.uint8)
                    relevantpixels = np.where(SkelMat == 1)
                    checkpixels = zip(relevantpixels[0], relevantpixels[1])
                    for (row, column) in checkpixels:
                        if self.abort is True:
                            break
                        #P1 = SkelMat[row,column]
                        B = 0
                        A = 0
                        P9 = SkelMat[row - 1, column - 1]
                        P2 = SkelMat[row - 1, column]
                        P3 = SkelMat[row - 1, column + 1]
                        P4 = SkelMat[row, column + 1]
                        P5 = SkelMat[row + 1, column + 1]
                        P6 = SkelMat[row + 1, column]
                        P7 = SkelMat[row + 1, column - 1]
                        P8 = SkelMat[row, column - 1]
                        if P2 > 0:
                            B = B + 1
                            if P9 == 0:
                                A = A + 1
                        if P3 > 0:
                            B = B + 1
                            if P2 == 0:
                                A = A + 1
                        if P4 > 0:
                            B = B + 1
                            if P3 == 0:
                                A = A + 1
                        if P5 > 0:
                            B = B + 1
                            if P4 == 0:
                                A = A + 1
                        if P6 > 0:
                            B = B + 1
                            if P5 == 0:
                                A = A + 1
                        if P7 > 0:
                            B = B + 1
                            if P6 == 0:
                                A = A + 1
                        if P8 > 0:
                            B = B + 1
                            if P7 == 0:
                                A = A + 1
                        if P9 > 0:
                            B = B + 1
                            if P8 == 0:
                                A = A + 1
                        tozero = (B >= 2 and B <= 6 and A == 1 and
                                  (P2 == 0 or P4 == 0 or P8 == 0) and
                                  (P2 == 0 or P6 == 0 or P8 == 0))
#                                  (P2 == 0 or P4 == 0 or P8 == 0 or
#                                   P2 > 1 or P4 > 1 or P8 > 1) and
#                                  (P2 == 0 or P6 == 0 or P8 == 0 or
#                                   P2 > 1 or P6 > 1 or P8 > 1))
##                                 (P2 * P4 * P8 == 0) and
##                                 (P2 * P6 * P8 == 0))
###                                          (P2 * P4 * P8 != 1) and
###                                          (P2 * P6 * P8 != 1))
                        if tozero:
                            #numChanges = numChanges + 1
                            changes = True
                            newSkelMat[row, column] = 0
                        #self.calculate_progress()
                    self.status.emit('1b')
                    #self.status.emit('Step 1 top left finished')
                    SkelMat = newSkelMat
                    #changes = False
                self.status.emit('Step 1 finished')
                #self.status.emit('#changes: ' + str(numChanges))
                self.status.emit('Number of iterations: ' + str(iterations))
                # Do step 2 (B>=7) (deletes completely contained
                #                   pixels and some others)
                # Could break bridges (!) if run independently:
                # ******
                #   **
                # ******
                #numChanges = 0
                newSkelMat = np.array(SkelMat, dtype=np.uint8)
                #newSkelMat = np.zeros((height + 2, width + 2), dtype=np.uint8)
                #newSkelMat = np.zeros((height + 2, width + 2), dtype=np.int16)
                relevantpixels = np.where(SkelMat == 1)
                checkpixels = zip(relevantpixels[0], relevantpixels[1])
                for (row, column) in checkpixels:
                    if self.abort is True:
                        break
                    #P1 = SkelMat[row, column]
                    B = 0
                    P2 = SkelMat[row - 1, column]
                    P3 = SkelMat[row - 1, column + 1]
                    P4 = SkelMat[row, column + 1]
                    P5 = SkelMat[row + 1, column + 1]
                    P6 = SkelMat[row + 1, column]
                    P7 = SkelMat[row + 1, column - 1]
                    P8 = SkelMat[row, column - 1]
                    P9 = SkelMat[row - 1, column - 1]
                    if P2:
                        B = B + 1
                    if P3:
                        B = B + 1
                    if P4:
                        B = B + 1
                    if P5:
                        B = B + 1
                    if P6:
                        B = B + 1
                    if P7:
                        B = B + 1
                    if P8:
                        B = B + 1
                    if P9:
                        B = B + 1
                    # Got to simple 9-connectedness
                    #fourer = (((P2+P3+P4==0) and (P6*P8>0)) or
                    #          ((P4+P5+P6==0) and (P8*P2>0)) or
                    #          ((P6+P7+P8==0) and (P2*P4>0)) or
                    #          ((P8+P9+P2==0) and (P4*P6>0)))
                    tozero = (B >= 7)
                    #if tozero or fourer:
                    if tozero:
                        newSkelMat[row, column] = 0
                        #numChanges = numChanges + 1
                SkelMat = newSkelMat
                self.status.emit('Step 2 finished')
                #self.status.emit('Step 2 finished - #changes: ' +
                #                                 str(numChanges))

                self.status.emit('Finished with level ' + str(level))
                self.status.emit('Skeleton matrix - ' + str(np.sum(SkelMat)))
                #SkelMatrices.append(SkelMat[1:-1,1:-1])
                self.calculate_levelprogress()
            # Final step:
            # Remove pixels to get to simple 9-connectedness
            #for row in range (1,height+1):
            #    if self.abort is True:
            #        break
            #    for column in range (1,width+1):
            #        if self.abort is True:
            #            break
            #        P1 = SkelMat[row,column]
            #        if P1 >= 1:  # only check non-zero pixels
            #            P2 = SkelMat[row-1,column]
            #           P3 = SkelMat[row-1,column+1]
            #            P4 = SkelMat[row,column+1]
            #            P5 = SkelMat[row+1,column+1]
            #            P6 = SkelMat[row+1,column]
            #            P7 = SkelMat[row+1,column-1]
            #            P8 = SkelMat[row,column-1]
            #            P9 = SkelMat[row-1,column-1]
            #            fourer = (((P2+P3+P4==0) and (P6*P8>0)) or
            #                      ((P4+P5+P6==0) and (P8*P2>0)) or
            #                      ((P6+P7+P8==0) and (P2*P4>0)) or
            #                      ((P8+P9+P2==0) and (P4*P6>0)))
            #            # # Remove 4-neighbours at crosses
            #            # otherfourer = (((P2*P6>0) and (P8==0) and P4>0) or
            #            #                ((P4*P8>0) and (P2==0) and P6>0) or
            #            #                ((P6*P2>0) and (P4==0) and P8>0) or
            #            #                ((P8*P4>0) and (P6==0) and P2>0))
            #            # if fourer or otherfourer:
            #            if fourer:
            #                SkelMat[row,column] = 0
            #                #numChanges = numChanges + 1
            #SkelMatrices.append(SkelMat[1:-1,1:-1])
            # Remove the edge from the matrix
            #self.status.emit('Matrix dimensions: ' + str(SkelMat.shape))
            result = SkelMat[1:-1, 1:-1]
            #self.status.emit('Matrix dimensions 2: ' + str(result.shape))
            #    self.calculate_progress()
        except:
            import traceback
            self.error.emit(traceback.format_exc())
            self.finished.emit(False, None)
        else:
            if self.abort:
                self.finished.emit(False, None)
            else:
                self.status.emit('Delivering the memory layer...')
                self.finished.emit(True, result)
                #self.finished.emit(True, SkelMatrices)
                #self.finished.emit(True, None)

    def calculate_progress(self):
        '''Update progress and emit a signal with the percentage'''
        self.processed = self.processed + 0.5  # Two times
        # update the progress bar at certain increments
        if (self.increment == 0 or
                self.processed % self.increment == 0):
            perc_new = (self.processed * 100) / self.numberofrows
            if perc_new > self.percentage:
                self.percentage = perc_new
                self.progress.emit(self.percentage)

    def calculate_levelprogress(self):
        '''Update progress and emit a signal with the percentage'''
        self.levelsprocessed = self.levelsprocessed + 1  #
        # update the progress bar at certain increments
        if (self.levelincrement == 0 or
                self.levelsprocessed % self.levelincrement == 0):
            perc_new = (self.levelsprocessed * 100) / self.numberoflevels
            if perc_new > self.levelspercentage:
                self.levelspercentage = perc_new
                self.progress.emit(self.levelspercentage)

    def kill(self):
        '''Kill the thread by setting the abort flag'''
        self.abort = True

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('NNJoinEngine', message)
