# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ThinGreyscale
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
import os.path
from PyQt4.QtCore import QSettings, QTranslator, qVersion
from PyQt4.QtCore import QCoreApplication
from PyQt4.QtGui import QAction, QIcon
from qgis.core import QgsMapLayer
#from qgis.core import QgsMessageLog

# Initialize Qt resources from file resources.py
import resources_rc
# Import the code for the dialog
from ThinGreyscale_dialog import ThinGreyscaleDialog


class ThinGreyscale:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'ThinGreyscale_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg = ThinGreyscaleDialog(self.iface)

        # Declare instance attributes
        self.THINGRAYSCALE = self.tr(u'&Thin greyscale image to skeleton')
        self.THINGRAYSCALEAMP = self.tr('&ThinGreyscale')
        self.menu = self.THINGRAYSCALE
        # TODO: We are going to let the user set this up in a future iteration
        #self.toolbar = self.iface.addToolBar(u'ThinGreyscale')
        #self.toolbar.setObjectName(u'ThinGreyscale')

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('ThinGreyscale', message)

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = ':/plugins/ThinGreyscale/icon.png'
        self.action = QAction(
            QIcon(icon_path),
            self.menu, self.iface.mainWindow())
        # connect the action to the run method
        self.action.triggered.connect(self.run)
        # Add menu item and Add toolbar icon
        if hasattr(self.iface, 'addPluginToRasterMenu'):
            self.iface.addPluginToRasterMenu(self.menu, self.action)
            self.iface.addRasterToolBarIcon(self.action)
        else:
            self.iface.addPluginToMenu(self.menu, self.action)
            self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        if hasattr(self.iface, 'removePluginRasterMenu'):
            self.iface.removePluginRasterMenu(self.menu, self.action)
            self.iface.removeRasterToolBarIcon(self.action)
        else:
            self.iface.removePluginMenu(self.menu, self.action)
            self.iface.removeToolBarIcon(self.action)

    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()

        self.dlg.progressBar.setValue(0.0)
        # Populate the inputRaster comboBox
        # Should also check for the type of raster (must be
        # singleband grayscale)
        self.dlg.inputRaster.clear()
        for alayer in self.iface.legendInterface().layers():
            gdalmetadata = alayer.metadata()
            # Skip WMS layers
            WMSstring = 'Web Map Service'
            wmspos = gdalmetadata.find(WMSstring)
            if wmspos != -1:
                continue
            provstring = '<p>GDAL provider</p>\n'
            providerpos = gdalmetadata.find(provstring)
            #if providerpos == -1:
            #    continue
            brpos = gdalmetadata.find('<br>', providerpos + len(provstring))
            aftprovpos = int(providerpos + len(provstring))
            gdalprovider = gdalmetadata[aftprovpos:int(brpos)]
            if alayer.type() == QgsMapLayer.RasterLayer:
                self.dlg.inputRaster.addItem(alayer.name(), alayer.id())
        # show the dialog (needed for the messagebar cancel button)
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        #if result:
        #   pass
        #QgsMessageLog.logMessage('Run method finished.',
        #                          self.dlg.THINGREYSCALE,
        #                               QgsMessageLog.INFO)
