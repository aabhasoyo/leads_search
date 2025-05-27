"""
    Miscellaneous utilities for MS 365 activities.
"""


import string
import re


def xl_col2num(col):
    """
        Convert an alphabetic column to a numerical column.
        https://stackoverflow.com/a/12640614
    """
    num = 0
    for c in col:
        if c in string.ascii_letters:
            num = num * 26 + (ord(c.upper()) - ord('A')) + 1
    return num


def xl_num2col(num):
    """
        Convert a column number to an alphabetic column.
        https://stackoverflow.com/a/23862195
    """
    s = ''
    while num > 0:
        num, rem = divmod(num - 1, 26)
        s = chr(65 + rem) + s
    return s


def xl_add2col(start, addition):
    """
        Add a number of columns to an alphabetic Excel column, getting the target column name.
    """
    return xl_num2col(xl_col2num(start) + addition)


def xl_parse_cell_address(address):
    """
        Parse an A1-style cell address.  If provided as a range (i.e. B2:D4), will ignore the second cell address.
        Returns two outputs, one string and one integer.
    """
    col = re.findall('[A-Z]+', address)[0]
    row = int(re.findall('[0-9]+', address)[0])
    return col, row


def xl_shift_cell(address, row_shift=0, col_shift=0):
    """
        Accept a cell address, and shift it by a given number of rows and columns, returning the final address.
    """
    col, row = xl_parse_cell_address(address)
    new_col = xl_add2col(col, col_shift)
    new_row = row + row_shift
    return f'{new_col}{new_row}'


def get_drive_item_ids(item):
    """
        Extract the Drive ID and Item ID for a DriveItem, return the API endpoint too.
    """
    drive_id = item.get('parentReference').get('driveId')
    item_id = item.get('id')
    return f'/drives/{drive_id}/items/{item_id}', drive_id, item_id
