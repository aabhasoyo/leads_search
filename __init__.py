"""
    Internal OYO package for Python interaction with Microsoft 365.
"""


__version__ = '0.1.8.4'
__author__ = 'Stephen Lee'


from .excel import WorkbookClient
from .drive import DriveClient
from .teams import TeamsClient
from .outlook import OutlookClient
from .auth import AuthConfig
