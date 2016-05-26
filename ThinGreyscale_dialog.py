# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ThinGreyscaleDialog
                                 A QGIS plugin
 Thin a greyscale image to a skeleton
                             -------------------
        begin                : 2014-12-22
        git sha              : $Format:%H$
        copyright            : (C) 2014 by Håvard Tveite, NMBU
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

from os.path import dirname, join, splitext, expanduser
from math import isnan, ceil
from tempfile import NamedTemporaryFile
from tempfile import mktemp
import numpy as np

from PyQt4 import uic
#from PyQt4.QtCore import QUrl
from PyQt4.QtCore import SIGNAL, QObject, QThread, Qt, QFileInfo
from PyQt4.QtCore import QCoreApplication, QSettings
from PyQt4.QtCore import QPointF, QRectF, QPoint
from PyQt4.QtGui import QDialog, QDialogButtonBox, QProgressBar
from PyQt4.QtGui import QPushButton, QFileDialog
#from PyQt4.QtGui import QDesktopServices
from PyQt4.QtGui import QGraphicsLineItem, QGraphicsRectItem
from PyQt4.QtGui import QGraphicsScene, QBrush, QPen, QColor
from PyQt4.QtGui import QGraphicsView
from PyQt4.QtGui import QStandardItem, QStandardItemModel

from qgis.core import QgsMessageLog, QgsMapLayerRegistry
from qgis.core import QGis, QgsMapLayer, QgsRasterLayer
from qgis.gui import QgsMessageBar
from osgeo import gdal

from ThinGreyscaleEngine import Worker


FORM_CLASS, _ = uic.loadUiType(join(
    dirname(__file__), 'ThinGreyscale_dialog_base.ui'))


class ThinGreyscaleDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        self.iface = iface
        self.plugin_dir = dirname(__file__)
        self.THINGREYSCALE = self.tr('ThinGreyscale')
        self.BROWSE = self.tr('Browse')
        self.CANCEL = self.tr('Cancel')
        self.CLOSE = self.tr('Close')
        self.OK = self.tr('OK')
        self.DEFAULTPROVIDER = 'GTiff'
        self.DEFAULTEXTENSION = '.tif'
        self.EXTRAEXTENSION = ' *.tiff'
        super(ThinGreyscaleDialog, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        okButton = self.button_box.button(QDialogButtonBox.Ok)
        okButton.setText(self.OK)
        cancelButton = self.button_box.button(QDialogButtonBox.Cancel)
        cancelButton.setText(self.CANCEL)
        cancelButton.setEnabled(False)
        closeButton = self.button_box.button(QDialogButtonBox.Close)
        closeButton.setText(self.CLOSE)
        browseButton = self.browseButton
        browseButton.setText(self.BROWSE)
        self.calcHistPushButton.setEnabled(False)
        self.listModel = QStandardItemModel(self.levelsListView)
        self.levelsListView.setModel(self.listModel)
        self.levelsListView.sizeHintForColumn(20)
        #self.levelValuesCheckBox.setEnabled(False)

        # Connect signals
        okButton.clicked.connect(self.startWorker)
        cancelButton.clicked.connect(self.killWorker)
        closeButton.clicked.connect(self.reject)
        browseButton.clicked.connect(self.browse)

        inpIndexCh = self.inputRaster.currentIndexChanged['QString']
        inpIndexCh.connect(self.layerchanged)
        bandCh = self.bandComboBox.currentIndexChanged['QString']
        bandCh.connect(self.bandChanged)
        #self.iface.legendInterface().itemAdded.connect(
        #    self.layerlistchanged)
        #self.iface.legendInterface().itemRemoved.connect(
        #    self.layerlistchanged)
        QObject.disconnect(self.button_box, SIGNAL("rejected()"), self.reject)
        calchistPr = self.calcHistPushButton.clicked
        calchistPr.connect(self.calculateHistogram)
        sugglevPr = self.suggestlevelsPushButton.clicked
        sugglevPr.connect(self.suggestLevels)
        addlevPr = self.addlevelPushButton.clicked
        addlevPr.connect(self.addLevel)
        dellevPr = self.deletelevelsPushButton.clicked
        dellevPr.connect(self.removeLevel)

        maxvalCh = self.maxValueSpinBox.valueChanged
        maxvalCh.connect(self.minmaxvalueChanged)
        maxvalFi = self.maxValueSpinBox.editingFinished
        maxvalFi.connect(self.minmaxvalueEdFinished)
        minvalCh = self.minValueSpinBox.valueChanged
        minvalCh.connect(self.minmaxvalueChanged)
        minvalFi = self.minValueSpinBox.editingFinished
        minvalFi.connect(self.minmaxvalueEdFinished)

        # Set instance variables
        #self.mem_layer = None
        self.worker = None
        self.inputlayerid = None
        self.inputlayer = None
        self.layerlistchanging = False
        self.minvalue = 1
        self.inputrasterprovider = None
        self.histobins = 50
        self.setupScene = QGraphicsScene(self)
        self.histoGraphicsView.setScene(self.setupScene)
        # Is the layer band of an integer type
        self.intband = False
        self.histogramAvailable = False
        self.histo = None
        self.histopadding = 1

    def startWorker(self):
        """Initialises and starts the worker thread."""
        try:
            layerindex = self.inputRaster.currentIndex()
            layerId = self.inputRaster.itemData(layerindex)
            inputlayer = QgsMapLayerRegistry.instance().mapLayer(layerId)
            if inputlayer is None:
                self.showError(self.tr('No input layer defined'))
                return
            # create a reference to the layer that is being processed
            # (for use when creating the resulting raster layer)
            self.thinninglayer = inputlayer
            self.levels = []
            #self.levelsListView.selectAll()
            #selected = self.levelsListView.selectedIndexes()
            if self.levelsListView.model().rowCount() == 0:
                self.showInfo("Levels must be specified!")
                return
            for i in range(self.levelsListView.model().rowCount()):
                levelstring = self.levelsListView.model().item(i).text()
            #for i in selected:
            #    levelstring = self.levelsListView.model().itemData(i)[0]
                if self.intband:
                    self.levels.append(int(levelstring))
                else:
                    self.levels.append(float(levelstring))
            #self.levelsListView.clearSelection()
            # create a new worker instance
            worker = Worker(inputlayer, self.levels, self.intband)
            # configure the QgsMessageBar
            msgBar = self.iface.messageBar().createMessage(
                                        self.tr('Skeletonising'), '')
            self.aprogressBar = QProgressBar()
            self.aprogressBar.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            acancelButton = QPushButton()
            acancelButton.setText(self.CANCEL)
            acancelButton.clicked.connect(self.killWorker)
            msgBar.layout().addWidget(self.aprogressBar)
            msgBar.layout().addWidget(acancelButton)
            # Has to be popped after the thread has finished (in
            # workerFinished).
            self.iface.messageBar().pushWidget(msgBar,
                                        self.iface.messageBar().INFO)
            self.messageBar = msgBar
            # start the worker in a new thread
            thread = QThread(self)
            worker.moveToThread(thread)
            worker.finished.connect(self.workerFinished)
            worker.error.connect(self.workerError)
            worker.status.connect(self.workerInfo)
            worker.progress.connect(self.progressBar.setValue)
            worker.progress.connect(self.aprogressBar.setValue)
            worker.iterprogress.connect(self.iterProgressBar.setValue)
            thread.started.connect(worker.run)
            thread.start()
            self.thread = thread
            self.worker = worker
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
            self.button_box.button(QDialogButtonBox.Close).setEnabled(False)
            self.button_box.button(QDialogButtonBox.Cancel).setEnabled(True)
        except:
            import traceback
            self.showError(traceback.format_exc())
        else:
            pass

    def workerFinished(self, ok, ret):
        """Handles the output from the worker and cleans up after the
           worker has finished."""
        # clean up the worker and thread
        #self.showInfo("Handling the result")
        self.worker.deleteLater()
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()
        # remove widget from message bar (pop)
        self.iface.messageBar().popWidget(self.messageBar)
        if ok and ret is not None:
            #self.showInfo("Ret: "+str(ret[10,]))
            # Transformation:
            self.minx = self.thinninglayer.extent().xMinimum()
            self.maxx = self.thinninglayer.extent().xMaximum()
            self.miny = self.thinninglayer.extent().yMinimum()
            self.maxy = self.thinninglayer.extent().yMaximum()
            self.rows = self.thinninglayer.height()
            self.cols = self.thinninglayer.width()
            self.xres = (self.maxx - self.minx) / float(self.cols)
            self.yres = (self.maxy - self.miny) / float(self.rows)
            geotransform = (self.minx, self.xres, 0, self.maxy, 0, -self.yres)
            try:
                format = self.DEFAULTPROVIDER
                driver = gdal.GetDriverByName(format)
                NOVALUE = 0
                metadata = driver.GetMetadata()
                fileName = self.outputRaster.text()
                if self.outputRaster.text() == "":
                    self.showInfo("No output file specified, " +
                                         "creating a temporary file")
                    # Get a temporary file
                    fileName = mktemp(prefix='greyskel',
                           suffix=self.DEFAULTEXTENSION)
                fileInfo = QFileInfo(fileName)
                filepath = fileInfo.absolutePath()
                baseName = fileInfo.baseName()
                suffix = fileInfo.suffix()
                thisfilename = filepath + baseName + '.' + suffix
                thisfilename = fileName
                self.showInfo("File name: " + thisfilename)
                gdaldatatype = gdal.GDT_Byte
                skelmatrix = None
                if self.levelValuesCheckBox.isChecked():
                    # Transform the pixel values back to the original
                    # level values
                    my_dict = {}
                    # Add zero to handle the "empty" pixels
                    my_dict[0] = 0
                    for i in range(len(self.levels)):
                        my_dict[i + 1] = self.levels[i]
                    skelmatrix = np.vectorize(my_dict.__getitem__,
                                              otypes=[np.float])(ret)
                    gdaldatatype = gdal.GDT_Int32
                    if not self.intband:
                        gdaldatatype = gdal.GDT_Float32
                else:
                    skelmatrix = ret
                outDataset = driver.Create(thisfilename, self.cols,
                                           self.rows, 1, gdaldatatype)
                if self.thinninglayer.dataProvider().crs() is not None:
                    srs = self.thinninglayer.dataProvider().crs()
                    outDataset.SetProjection(srs.toWkt().encode('ascii',
                                                               'ignore'))
                skeletonband = outDataset.GetRasterBand(1)
                skeletonband.WriteArray(skelmatrix)
                skeletonband.SetNoDataValue(NOVALUE)
                #stats = skeletonband.GetStatistics(False, True)
                #skeletonband.SetStatistics(stats[0], stats[1],
                #                                 stats[2], stats[3])
                outDataset.SetGeoTransform(geotransform)
                outDataset = None  # To close the file
                # report the result
                rlayer = QgsRasterLayer(thisfilename, baseName)
                self.layerlistchanging = True
                QgsMapLayerRegistry.instance().addMapLayer(rlayer)
                self.layerlistchanging = False
            except:
                import traceback
                self.showError("Can't write the skeleton file:  %s" %
                                   self.outputRaster.text() + ' - ' +
                                   traceback.format_exc())
                okb = self.button_box.button(QDialogButtonBox.Ok)
                okb.setEnabled(True)
                closb = self.button_box.button(QDialogButtonBox.Close)
                closb.setEnabled(True)
                cancb = self.button_box.button(QDialogButtonBox.Cancel)
                cancb.setEnabled(False)
                return
            QgsMessageLog.logMessage(self.tr('ThinGreyscale finished'),
                                self.THINGREYSCALE, QgsMessageLog.INFO)
        else:
            # notify the user that something went wrong
            if not ok:
                self.showError(self.tr('Aborted') + '!')
            else:
                self.showError(self.tr('No skeleton created') + '!')
        self.progressBar.setValue(0.0)
        #self.aprogressBar.setValue(0.0)
        self.iterProgressBar.setValue(0.0)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
        self.button_box.button(QDialogButtonBox.Close).setEnabled(True)
        self.button_box.button(QDialogButtonBox.Cancel).setEnabled(False)

    def workerError(self, exception_string):
        """Report an error from the worker."""
        #QgsMessageLog.logMessage(self.tr('Worker failed - exception') +
        #                         ': ' + str(exception_string),
        #                         self.THINGREYSCALE,
        #                         QgsMessageLog.CRITICAL)
        self.showError(exception_string)

    def workerInfo(self, message_string):
        """Report an info message from the worker."""
        QgsMessageLog.logMessage(self.tr('Worker') + ': ' + message_string,
                                 self.THINGREYSCALE, QgsMessageLog.INFO)

    def layerchanged(self, number=0):
        """Do the necessary updates after a layer selection has
           been changed."""
        # If the layer list is being updated, don't do anything
        if self.layerlistchanging:
            return
        layerindex = self.inputRaster.currentIndex()
        layerId = self.inputRaster.itemData(layerindex)
        self.inputlayerid = layerId
        self.inputlayer = QgsMapLayerRegistry.instance().mapLayer(layerId)
        if self.inputlayer is not None:
            self.inputrasterprovider = self.inputlayer.dataProvider()
            self.bandComboBox.clear()
            bandcount = self.inputlayer.bandCount()
            #self.showInfo("Layer bandcount: "+str(bandcount))
            for i in range(bandcount):
                self.bandComboBox.addItem(self.inputlayer.bandName(i + 1), i)
                #self.showInfo("Band " + str(i) + ": " +
                #                self.inputlayer.bandName(i+1))
            # Check if the driver supports Create() or CreateCopy()
            #gdalmetadata = self.inputlayer.metadata()
            #self.showInfo("Layer metadata: " +
            #                str(gdalmetadata.encode('utf-8')))
            #provstring = '<p>GDAL provider</p>\n'
            #providerpos = gdalmetadata.find(provstring)
            #brpos = gdalmetadata.find('<br>', providerpos + len(provstring))
            #self.gdalprovider = gdalmetadata[int(providerpos +
            #                             len(provstring)):int(brpos)]
            #self.showInfo('GDAL provider: '+self.gdalprovider)
            #drivername = self.gdalprovider.encode('ascii', 'ignore')
            #theDriver = gdal.GetDriverByName(drivername)
            #if theDriver is None:
            #    self.showInfo("Unable to get the raster driver")
            #else:
            #data    theMetadata = theDriver.GetMetadata()
                #self.showInfo("Driver metadata: "+str(theMetadata))
                #if ((gdal.DCAP_CREATE in theMetadata) and
                #        theMetadata[gdal.DCAP_CREATE] == 'YES'):
                #    self.canCreate = True
                #if (theMetadata.has_key(gdal.DCAP_CREATECOPY) and
                #if ((gdal.DCAP_CREATECOPY in theMetadata) and
                #        theMetadata[gdal.DCAP_CREATECOPY] == 'YES'):
                #    self.canCreateCopy = True
                #self.showInfo('raster provider type: ' +
                #                str(self.inputlayer.providerType()))
                # Determine the file suffix
                #self.gdalext = ""
                #if gdal.DMD_EXTENSION in theMetadata:
                #    self.gdalext = "." + theMetadata[gdal.DMD_EXTENSION]
                #else:
                #    self.showInfo("No extension available in GDAL metadata")
                # by parsing the layer metadata looking for
                #           "Dataset Description"
                #descstring = 'Dataset Description</p>\n<p>'
                #descpos = gdalmetadata.find(descstring)
                #ppos = gdalmetadata.find('</p>',descpos+len(descstring))
                #filename = gdalmetadata[descpos+len(descstring):ppos]
                #self.gdalext = splitext(filename)[1]
                #self.showInfo('GDAL extension: '+self.gdalext)
                # Determine the datatype
                #datatypestring = 'Data Type</p>\n<p>'
                #datatypepos = gdalmetadata.find(datatypestring)
                #ppos = gdalmetadata.find('</p>',
                #                   datatypepos + len(datatypestring))
                #datatypedesc = gdalmetadata[datatypepos +
                #                            len(datatypestring):ppos]
                #shortdesc = datatypedesc.split()[0]
                #self.showInfo('GDAL data type: GDT_'+shortdesc)
                # Call the findGdalDatatype function
                #self.findGdalDatatype(shortdesc)
            #   self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
            self.calcHistPushButton.setEnabled(True)
            self.suggestlevelsPushButton.setEnabled(True)

    def bandChanged(self):
        band = self.bandComboBox.currentIndex() + 1
        #self.showInfo("Band changed: " + str(band))
        statistics = self.inputrasterprovider.bandStatistics(band)
        #self.showInfo("Band statistics: " + str(statistics.minimumValue) +
        #                            " - " + str(statistics.maximumValue) +
        #                            " - " + str(statistics.mean))
        self.bandmin = statistics.minimumValue
        self.bandmax = statistics.maximumValue
        dt = self.inputrasterprovider.dataType(band)
        # Integer data type
        if (dt == QGis.Byte or dt == QGis.UInt16 or dt == QGis.Int16
                            or dt == QGis.UInt32 or dt == QGis.Int32):
            self.intband = True
            self.minValueSpinBox.setDecimals(0)
            self.maxValueSpinBox.setDecimals(0)
            self.levelSpinBox.setDecimals(0)
            self.bandMinLabel.setText(str(int(statistics.minimumValue)))
            self.bandMaxLabel.setText(str(int(statistics.maximumValue)))
        else:
            self.intband = False
            self.minValueSpinBox.setDecimals(5)
            self.maxValueSpinBox.setDecimals(5)
            self.levelSpinBox.setDecimals(5)
            minlabtext = "{0:.5f}".format(statistics.minimumValue)
            self.bandMinLabel.setText(minlabtext)
            maxlabtext = "{0:.5f}".format(statistics.maximumValue)
            self.bandMaxLabel.setText(maxlabtext)
        #self.minValueSpinBox.setMinimum(statistics.minimumValue)
        self.maxValueSpinBox.setMinimum(statistics.minimumValue)
        #self.minValueSpinBox.setMaximum(statistics.maximumValue)
        self.maxValueSpinBox.setMaximum(statistics.maximumValue)
        #self.minValueSpinBox.setValue(statistics.minimumValue)
        if not (statistics.statsGathered & statistics.Mean):
            bandmean = (statistics.minimumValue + statistics.maximumValue) / 2
        else:
            #self.showInfo("statsgathered: " + str(statistics.statsGathered))
            bandmean = statistics.mean
        if self.intband:
            self.minValueSpinBox.setValue(int(ceil(bandmean)))
        else:
            self.minValueSpinBox.setValue(bandmean)
        self.maxValueSpinBox.setValue(statistics.maximumValue)
        self.histMinValue.setText(str(statistics.minimumValue))
        self.histMaxValue.setText(str(statistics.maximumValue))
        self.levelSpinBox.setMinimum(statistics.minimumValue)
        self.levelSpinBox.setMaximum(statistics.maximumValue)
        self.histogramAvailable = False
        #if self.inputrasterprovider.hasStatistics(band):
        #if statistics.statsGathered:
            #histogram = statistics.histogramVector
            #self.showInfo("Histogram: " + str(histogram))
            #range = min to max
            #np.histogram(band, 50, range)

    def minmaxvalueChanged(self):
        #if self.minValueSpinBox is None:
        #    return
        minvalue = self.minValueSpinBox.value()
        #if minvalue is None:
        #    return
        #if self.maxValueSpinBox is None:
        #    return
        maxvalue = self.maxValueSpinBox.value()
        #if maxvalue is None:
        #   return
        if isnan(maxvalue) or isnan(minvalue):
            return
        #self.showInfo("minvalue: " + str(minvalue) + " Maxvalue: " +
        #                                               str(maxvalue))
        #if self.intband:
        #    minvalue = int(minvalue)
        #    maxvalue = int(maxvalue)
        if abs(maxvalue - minvalue) < 0.00001:
        #if maxvalue == maxvalue:
            self.calcHistPushButton.setEnabled(False)
        else:
            self.calcHistPushButton.setEnabled(True)
        # Update the min and max value spinboxes
        self.minValueSpinBox.setMaximum(maxvalue)
        self.maxValueSpinBox.setMinimum(minvalue)
        self.minValueSpinBox.setMinimum(self.bandmin)

    def minmaxvalueEdFinished(self):
        minvalue = self.minValueSpinBox.value()
        maxvalue = self.maxValueSpinBox.value()
        if self.intband:
            minvalue = int(minvalue)
            maxvalue = int(maxvalue)
        #self.showInfo("minvalue: " + str(minvalue) + " Maxvalue: " +
        #                            str(maxvalue))
        # Update the spin box for adding levels
        self.levelSpinBox.setMinimum(minvalue)
        self.levelSpinBox.setMaximum(maxvalue)
        if self.levelSpinBox.value() < minvalue:
            self.levelSpinBox.setValue(minvalue)
        if self.levelSpinBox.value() > maxvalue:
            self.levelSpinBox.setValue(maxvalue)
        # Update the min and max value spinboxes
        self.minValueSpinBox.setMaximum(maxvalue)
        self.maxValueSpinBox.setMinimum(minvalue)

        # Adjust the levels:
        i = 0
        while self.levelsListView.model().item(i):
        #for i in range(self.levelsListView.model().rowCount()):
            #self.showInfo("Element: " +
            #       str(self.levelsListView.model().item(i).text()))
            #continue
            value = float(self.levelsListView.model().item(i).text())
            if value < minvalue:
                if i == 0:
                    self.levelsListView.model().item(i).setText(str(minvalue))
                    i = i + 1
                else:
                    self.levelsListView.model().removeRow(i)
            elif value > maxvalue:
                if i == self.levelsListView.model().rowCount() - 1:
                    self.levelsListView.model().item(i).setText(str(maxvalue))
                    i = i + 1
                else:
                    self.levelsListView.model().removeRow(i)
            else:
                i = i + 1
        self.drawHistogram()

    def calculateHistogram(self):
        if self.inputlayer is None:
            return
        #self.showInfo("Calculating histogram...")
        # Check if there is only one value
        myrange = (self.minValueSpinBox.value(), self.maxValueSpinBox.value())
        self.inputextent = self.inputlayer.extent()
        self.inputrdp = self.inputlayer.dataProvider()
        width = self.inputlayer.width()
        height = self.inputlayer.height()
        if width == 0 or height == 0:
            self.showInfo("Image has zero width or height")
            return
        extwidth = self.inputextent.width()
        extheight = self.inputextent.height()
        # Read the raster block and get the maximum value
        rasterblock = self.inputrdp.block(1, self.inputextent,
                                          width, height)
        # Create a numpy array version of the image
        imageMat = np.zeros((height, width), dtype=np.float16)
        # This one takes a lot of time!
        for row in range(height):
            for column in range(width):
                imageMat[row, column] = rasterblock.value(row, column)
        self.histo = np.histogram(imageMat, self.histobins, myrange)
        #relevantpixels = imageMat[np.where(imageMat >= bandval)]
        minlevel = float(self.bandMinLabel.text())
        relevantpixels = imageMat[np.where(imageMat >= minlevel)]
        #self.showInfo("Histogram: " + str(self.histo))
        nanpercentage = 100.0 - 100.0 * len(relevantpixels) / (width * height)
        self.bandNANLabel.setText("{0:.1f}".format(nanpercentage))
        #self.showInfo("Percentage NAN: " + str(100.0 - 100.0 *
        #                    len(relevantpixels) / (width * height)))
        #self.showInfo("First element: " + str(self.histo[0]))
        #self.showInfo("First element, first: " + str(self.histo[0][0]))
        #self.showInfo("First element, second: " + str(self.histo[0][1]))
        self.histMinValue.setText(str(self.minValueSpinBox.value()))
        self.histMaxValue.setText(str(self.maxValueSpinBox.value()))
        if self.intband:
            self.histMinValue.setText(str(int(self.minValueSpinBox.value())))
            self.histMaxValue.setText(str(int(self.maxValueSpinBox.value())))
        self.histogramAvailable = True
        self.drawHistogram()

    def drawHistogram(self):
        #if self.inputlayer is None:
        #    return
        #self.showInfo("Drawing histogram...")
        viewprect = QRectF(self.histoGraphicsView.viewport().rect())
        self.histoGraphicsView.setSceneRect(viewprect)
        self.setupScene.clear()
        self.setupScene.update()
        histbottom = self.histoGraphicsView.sceneRect().bottom()
        histtop = self.histoGraphicsView.sceneRect().top()
        left = self.histoGraphicsView.sceneRect().left() + self.histopadding
        right = self.histoGraphicsView.sceneRect().right() - self.histopadding
        histheight = histbottom - histtop
        histwidth = right - left
        step = 1.0 * histwidth / self.histobins
        maxlength = histheight
        padding = 1
        ll = QPoint(self.histopadding - 1, histheight - padding)
        start = QPointF(self.histoGraphicsView.mapToScene(ll))

        # Check if there is only one value
        #myrange = (self.minValueSpinBox.value(),self.maxValueSpinBox.value())
        if self.histogramAvailable:
            maxvalue = 0.0
            for i in range(len(self.histo[0])):
                if self.histo[0][i] > maxvalue:
                    maxvalue = self.histo[0][i]
            if maxvalue == 0:
                return
            self.maxBinNumber.setText(str(maxvalue))
            # Create the histogram:
            #self.showInfo("maxvalue: " + str(maxvalue))
            #self.showInfo("maxlength: " + str(maxlength))
            #self.showInfo("step: " + str(step))
            for i in range(self.histobins):
                binnumber = self.histo[0][i]
                if binnumber == 0:
                    continue
                height = (1.0 * self.histo[0][i] / maxvalue *
                                          (maxlength - padding))
                rectangle = QGraphicsRectItem(start.x() + step * i,
                                          start.y(),
                                          step,
                                          -height)
                rectangle.setPen(QPen(QColor(102, 102, 102)))
                rectangle.setBrush(QBrush(QColor(240, 240, 240)))
                self.setupScene.addItem(rectangle)
                #self.showInfo(str(i) + ": " + str(height))
            #if self.levelsListView.model().rowCount() > 0:
        # Add lines for the levels
        minvalue = float(self.histMinValue.text())
        maxvalue = float(self.histMaxValue.text())
        datarange = maxvalue - minvalue
        if datarange == 0:
            return
        i = 0
        while self.levelsListView.model().item(i):
            #self.showInfo("Element: " +
            #       str(self.levelsListView.model().item(i).text()))
            #continue
            value = float(self.levelsListView.model().item(i).text())
            xvalue = start.x() + histwidth * (value - minvalue) / datarange
            line = QGraphicsLineItem(xvalue, 0, xvalue, histheight)
            if i == 0 or i == (self.levelsListView.model().rowCount() - 1):
                line.setPen(QPen(QColor(204, 0, 0)))
            else:
                line.setPen(QPen(QColor(0, 204, 0)))
            self.setupScene.addItem(line)
            i = i + 1

    def suggestLevels(self):
        self.listModel.clear()
        #self.showInfo("Suggesting levels")
        levels = self.levelsSpinBox.value()
        startvalue = self.minValueSpinBox.value()
        endvalue = self.maxValueSpinBox.value()
        increment = (endvalue - startvalue) / levels
        for i in range(levels + 1):
            value = startvalue + increment * i
            if self.intband:
                value = int(value)
            item = QStandardItem(str(value))
            self.listModel.appendRow(item)
        self.drawHistogram()

    def addLevel(self):
        newvalue = self.levelSpinBox.value()
        if self.intband:
            newvalue = int(newvalue)
        for i in range(self.listModel.rowCount()):
            # Check if the value is already in the list
            if self.listModel.item(i).text() == str(newvalue):
                return
            else:
                # Maintain a sorted list of distances
                if (float(self.listModel.item(i).text()) >
                                 float(str(newvalue))):
                    item = QStandardItem(str(newvalue))
                    self.listModel.insertRow(i, item)
                    self.drawHistogram()
                    return
        item = QStandardItem(str(newvalue))
        self.listModel.appendRow(item)
        #if self.histogramAvailable:
        #    addLevelsToHistogram()
        self.drawHistogram()

    def removeLevel(self):
        self.levelsListView.setUpdatesEnabled(False)
        indexes = self.levelsListView.selectedIndexes()
        indexes.sort()
        for i in range(len(indexes) - 1, -1, -1):
            self.listModel.removeRow(indexes[i].row())
        self.levelsListView.setUpdatesEnabled(True)
        #if self.histogramAvailable:
        #    removeLevelFromHistogram()
        self.drawHistogram()

    def layerlistchanged(self):
        self.layerlistchanging = True
        # Repopulate the input layer combo box
        # Save the currently selected input layer
        inputlayerid = self.inputlayerid
        self.inputRaster.clear()
        for alayer in self.iface.legendInterface().layers():
            if alayer.type() == QgsMapLayer.RasterLayer:
                gdalmetadata = alayer.metadata()
                # Skip WMS layers
                WMSstring = 'Web Map Service'
                wmspos = gdalmetadata.find(WMSstring)
                if wmspos != -1:
                    continue
                self.inputRaster.addItem(alayer.name(), alayer.id())
        # Set the previous selection
        for i in range(self.inputRaster.count()):
            if self.inputRaster.itemData(i) == inputlayerid:
                self.inputRaster.setCurrentIndex(i)
        self.layerlistchanging = False
        #self.updateui()

    def updateui(self):
        """Do the necessary updates after a layer selection has
           been changed."""
        #if self.layerlistchanged:
        #    return
        #self.outputRaster.setText(self.inputRaster.currentText() +
        #                           '_' + 'thinned')
        layerindex = self.inputRaster.currentIndex()
        layerId = self.inputRaster.itemData(layerindex)
        inputlayer = QgsMapLayerRegistry.instance().mapLayer(layerId)
        if inputlayer is not None:
            pass
        else:
            pass

    def findGdalDatatype(self, shortdesc):
            gdaldatatype = None
            # // Unknown or unspecified type
            # GDT_Unknown = GDALDataType(C.GDT_Unknown)
            if shortdesc == 'Unknown':
                gdaldatatype = gdal.GDT_Unknown
            # // Eight bit unsigned integer
            # GDT_Byte = GDALDataType(C.GDT_Byte)
            elif shortdesc == 'Byte':
                gdaldatatype = gdal.GDT_Byte
            # // Sixteen bit unsigned integer
            # GDT_UInt16 = GDALDataType(C.GDT_UInt16)
            elif shortdesc == 'UInt16':
                gdaldatatype = gdal.GDT_UInt16
            # // Sixteen bit signed integer
            # GDT_Int16 = GDALDataType(C.GDT_Int16)
            elif shortdesc == 'Int16':
                gdaldatatype = gdal.GDT_Int16
            # // Thirty two bit unsigned integer
            # GDT_UInt32 = GDALDataType(C.GDT_UInt32)
            elif shortdesc == 'UInt32':
                gdaldatatype = gdal.GDT_UInt32
            # // Thirty two bit signed integer
            # GDT_Int32 = GDALDataType(C.GDT_Int32)
            elif shortdesc == 'Int32':
                gdaldatatype = gdal.GDT_Int32
            # // Thirty two bit floating point
            # GDT_Float32 = GDALDataType(C.GDT_Float32)
            elif shortdesc == 'Float32':
                gdaldatatype = gdal.GDT_Float32
            # // Sixty four bit floating point
            # GDT_Float64 = GDALDataType(C.GDT_Float64)
            elif shortdesc == 'Float64':
                gdaldatatype = gdal.GDT_Float64
            # // Complex Int16
            # GDT_CInt16 = GDALDataType(C.GDT_CInt16)
            elif shortdesc == 'CInt16':
                gdaldatatype = gdal.CInt16
            # // Complex Int32
            # GDT_CInt32 = GDALDataType(C.GDT_CInt32)
            elif shortdesc == 'CInt32':
                gdaldatatype = gdal.CInt32
            # // Complex Float32
            # GDT_CFloat32 = GDALDataType(C.GDT_CFloat32)
            elif shortdesc == 'CFloat32':
                gdaldatatype = gdal.CFloat32
            # // Complex Float64
            # GDT_CFloat64 = GDALDataType(C.GDT_CFloat64)
            elif shortdesc == 'CFloat64':
                gdaldatatype = gdal.CFloat64
            # // maximum type # + 1
            # GDT_TypeCount = GDALDataType(C.GDT_TypeCount)
            elif shortdesc == 'TypeCount':
                gdaldatatype = gdal.TypeCount
            self.gdaldatatype = gdaldatatype

    def killWorker(self):
        """Kill the worker thread."""
        if self.worker is not None:
            QgsMessageLog.logMessage(self.tr('Killing worker'),
                                     self.THINGREYSCALE, QgsMessageLog.INFO)
            self.worker.kill()

    def showError(self, text):
        """Show an error."""
        self.iface.messageBar().pushMessage(self.tr('Error'), text,
                                            level=QgsMessageBar.CRITICAL,
                                            duration=3)
        QgsMessageLog.logMessage('Error: ' + text, self.THINGREYSCALE,
                                 QgsMessageLog.CRITICAL)

    def showWarning(self, text):
        """Show a warning."""
        self.iface.messageBar().pushMessage(self.tr('Warning'), text,
                                            level=QgsMessageBar.WARNING,
                                            duration=2)
        QgsMessageLog.logMessage('Warning: ' + text, self.THINGREYSCALE,
                                 QgsMessageLog.WARNING)

    def showInfo(self, text):
        """Show info."""
        self.iface.messageBar().pushMessage(self.tr('Info'), text,
                                            level=QgsMessageBar.INFO,
                                            duration=2)
        QgsMessageLog.logMessage('Info: ' + text, self.THINGREYSCALE,
                                 QgsMessageLog.INFO)

    # def help(self):
        # #QDesktopServices.openUrl(QUrl.fromLocalFile(self.plugin_dir +
        #                                 "/help/build/html/index.html"))
        # QDesktopServices.openUrl(QUrl.fromLocalFile(self.plugin_dir +
        #                                            "/help/index.html"))
        # #showPluginHelp()

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        return QCoreApplication.translate('ThinGreyScaleDialog', message)

    def browse(self):
        settings = QSettings()
        key = '/UI/lastShapefileDir'
        outDir = settings.value(key)
        home = outDir
        #outDir = expanduser("~")
        #filter = (self.DEFAULTPROVIDER + " (*" +
        #             self.DEFAULTEXTENSION + ");;All files (*)")
        filter = (self.DEFAULTPROVIDER + " (*" +
                     self.DEFAULTEXTENSION + self.EXTRAEXTENSION + ")")
        #if (self.gdalprovider != self.DEFAULTPROVIDER and
        #                                     (self.canCreateCopy or
        #                                           self.canCreate)):
        #    filter = (self.gdalprovider + " (*" + self.gdalext +
        #                                          ");;" + filter)
        outFilePath = QFileDialog.getSaveFileName(self,
                                   'Specify file name for skeleton',
                                                     outDir, filter)
        outFilePath = unicode(outFilePath)
        if outFilePath:
            root, ext = splitext(outFilePath)
            if ext.lower() != '.tif' and ext.lower() != '.tiff':
                outFilePath = '%s.tif' % outFilePath
            outDir = dirname(outFilePath)
            settings.setValue(key, outDir)
        #        (self.canCreateCopy or self.canCreate):
        #    fileName = splitext(str(fileName))[0]+self.gdalext
        self.outputRaster.setText(outFilePath)

    # Overriding
    def resizeEvent(self, event):
        #self.showInfo("resizeEvent")
        self.calculateHistogram()

    # Implement the accept method to avoid exiting the dialog when
    # starting the work
    def accept(self):
        """Accept override."""
        pass

    # Implement the reject method to have the possibility to avoid
    # exiting the dialog when cancelling
    def reject(self):
        """Reject override."""
        # exit the dialog
        QDialog.reject(self)
