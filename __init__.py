# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ThinGreyscale
                                 A QGIS plugin
 Thin a greyscale image to a skeleton
                             -------------------
        begin                : 2014-12-22
        copyright            : (C) 2014 by Håvard Tveite, NMBU
        email                : havard.tveite@nmbu.no
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load ThinGreyscale class from file ThinGreyscale.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .ThinGreyscale import ThinGreyscale
    return ThinGreyscale(iface)
