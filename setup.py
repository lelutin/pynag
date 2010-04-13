#!/usr/bin/env python
#############################################################################
#                                                                           #
#    Nagios custom plugins -- A python library and a set of Nagios plugins. #
#    Copyright (C) 2010  Revolution Linux, inc. <info@revolutionlinux.com>  #
#                                                                           #
#    This program is free software: you can redistribute it and/or modify   #
#    it under the terms of the GNU General Public License as published by   #
#    the Free Software Foundation, either version 3 of the License, or      #
#    (at your option) any later version.                                    #
#                                                                           #
#    This program is distributed in the hope that it will be useful,        #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of         #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          #
#    GNU General Public License for more details.                           #
#                                                                           #
#    You should have received a copy of the GNU General Public License      #
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.  #
#                                                                           #
#############################################################################

"""setuptools setup script for the Nagios plugin Python library."""

#from setuptools import setup, find_packages
from distutils.core import setup

VERSION="1.0"

setup(name="nagpy",
    version=VERSION,
    description="Library that removes most of the repetitive work "
                "from coding a Nagios Plugin",
    author="Gabriel Filion",
    author_email="gfilion@revolutionlinux.com",
    url="http://www.revolutionlinux.com/",
    license="GPL",
    platforms=["Linux"],
    long_description="""
    This library provides a class that automates most tasks for Nagios plugins.
    It provides an automatic verbose mode, provides an automatic help option,
    timeouts after a defined number of seconds. And exits with the according
    code and message when the corresponding exception is raised during the
    check.
    """,
    keywords="nagios plugin",
    packages=["nagpy"],
    package_dir={"nagpy": "src/nagpy"}
)
