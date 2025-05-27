"""
    Clients designed to interact with Shared OneDrive Excel files.
"""


from .core import CoreClient
from .drive import DriveClient
from .misc import xl_shift_cell, get_drive_item_ids
import json
import base64
import pandas as pd
import numpy as np
from io import StringIO


class WorkbookClient(CoreClient):
    """
        Constructs a custom HTTPClient to be used for requests against an Excel Workbook.
        The requests methods here are augmented with the usage of Session IDs to make sequences
        of API calls as efficient as possible.

        This Client will act on behalf of an Azure User via an application registered through Azure AD.
    """

    def __init__(self, config, url='', drive_item=None, **kwargs):
        """
            Class constructor that accepts a Share URL to the desired Excel file.

            Args:
                config: An AuthConfig object configuring the Token Cache, or the username string.
                url: The Share URL must grant access to the Azure User used to log in with this Client.
                drive_item: Optional DriveItem dictionary, if the Item is already identified.
        """
        self.url = url
        self.drive_id = None
        self.item_id = None
        self.drive_item = drive_item

        # Super class acquires authorization and sets up the resource path
        super().__init__(config, scopes=['Files.ReadWrite.All'], **kwargs)

        # Next, set up a Session ID for use throughout the lifetime of the class instance
        self.session_id = ''
        self._refresh_session_id()
        

    def set_calculation_mode(self, mode="Automatic"):
        """
        Changes Excel calculation mode to "Manual" or "Automatic".
        :param mode: str, either "Manual" or "Automatic"
        """
        valid_modes = ["Automatic", "Manual"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode. Choose from {valid_modes}")
    
        # Correct endpoint according to Microsoft Graph API
        url = f"{self.resource_path}/application"
    
        calculation_mode = {
            "Automatic": "automatic",
            "Manual": "manual"
        }
    
        # Send PATCH request to update application settings
        self.patch(
            url,
            json={"calculationMode": calculation_mode[mode]},
            headers={"Content-Type": "application/json"}
        )
        print(f"✅ Excel calculation mode set to {mode}")


    def _custom_resource_path(self):
        """
            The custom resource path for a Workbook points to the specific Drive ID and Item ID.
            We execute the API call to find these IDs given the Share URL, then we use the IDs
            to construct the resource path.
        """
        # Shared URLs must be converted to the necessary format:
        # https://docs.microsoft.com/en-us/graph/api/shares-get?view=graph-rest-1.0&tabs=http#encoding-sharing-urls
        encode_url = base64.b64encode(bytes(self.url, 'utf-8'))
        encode_url = b'u!' + encode_url.strip(b'=').replace(b'/', b'_').replace(b'+', b'-')

        # Find the Drive and Item IDs for the Excel file, if we don't already have it
        if self.drive_item is None:
            self.drive_item = self.client.get(f'/shares/{encode_url.decode("utf-8")}/driveItem').json()
        url, self.drive_id, self.item_id = get_drive_item_ids(self.drive_item)

        if self.drive_id is None or self.item_id is None:
            raise ValueError('Excel Share URL or DriveItem is Invalid')

        # Construct the API path to the workbook
        self.resource_path = url + '/workbook'

    
    def _refresh_session_id(self):
        """
            Create/Refresh the Session ID for enabling maximize efficiency from the Graph API.
            Without usage of the Session feature, each API call would need to re-locate the file.
            https://docs.microsoft.com/en-us/graph/api/resources/excel?view=graph-rest-1.0#api-call-to-get-a-session
        """
        session_body = {'persistChanges': True}
        session_header = {'Content-Type': 'application/json'}
        session_res = self.client.post(f'{self.resource_path}/createSession',
                                       data=json.dumps(session_body),
                                       headers=session_header)
        self.session_id = session_res.json().get('id')

    def _custom_request(self, request_type, path, as_json=True, **kwargs):
        """
            Custom method to perform a request via the client using a Session.
            If the request fails with a known Session ID error, we refresh the Session and try once more.
        """
        input_header = kwargs.pop('headers', {})

        def session_request():
            session_header = {'workbook-session-id': self.session_id}
            return getattr(self.client, request_type)(path, headers={**input_header, **session_header}, **kwargs)
        res = session_request()

        # If we catch an Invalid Session error specifically, then retry once with a fresh Session
        if not res.ok and 'application/json' in res.headers.get('Content-Type', ''):
            if res.json().get('error', {}).get('code') == 'InvalidSession':
                self._refresh_session_id()
                res = session_request()

        return res

    def _close_session(self):
        """
            Best practice is to close the Session when finished.
        """
        if self.session_id:
            self.post('/closeSession', headers={'Content-type': 'application/json'})

    def get_sheet_list(self):
        """
            Acquire a list of sheet names belonging to the Workbook.
        """
        return [sheet.get('name') for sheet in self.get('/worksheets?$select=name').get('value')]

    def get_sheet(self, sheet_name):
        """
            Acquire an Object representing one Worksheet.
        """
        return SpreadsheetClient(sheet_name, workbook_client=self)

    def create_sheet(self, sheet_name):
        """
            Create a new sheet with the desired name.

            Args:
                sheet_name: Name of the desired sheet.
        """
        if sheet_name not in self.get_sheet_list():
            self.post('/worksheets', json={'name': sheet_name})

    def get_used_range_info(self, sheet_name, range_address=None):
        """
            Given a sheet (and possibly a range address), extract the Used Range information,
            namely the address, number of rows, and number of columns.
            Returns a tuple: (address, rows, cols)

            Args:
                sheet_name: Name of the desired sheet.
                range_address: Optional string with the Range address (A1 format).
        """
        if range_address is None:
            url = f"/worksheets/{sheet_name}/usedRange(valuesOnly=true)"
        else:
            url = f"/worksheets/{sheet_name}/range(address='{range_address}')/usedRange(valuesOnly=true)"

        # Get the range address, so we can chunk up the read action
        range_info = self.get(f'{url}?$select=address,rowCount,columnCount')
        return tuple(map(range_info.get, ['address', 'rowCount', 'columnCount']))

    def get_range_data(self, sheet_name, range_address=None, as_df=True, nan_errors=None, chunk_size=500000, **kwargs):
        """
            Read the data from a given range, provided a Sheet name and (optional) Range Address.

            Args:
                sheet_name: Name of the desired sheet.
                range_address: Optional string with the Range address (A1 format).
                as_df: Optional Boolean deciding if the results are desired as a DataFrame.
                nan_errors: Optional List of Excel errors to explicitly replace as NaN. Otherwise, defaults to:
                    ['#DIV/0!', '#N/A', '#NAME?', '#NULL!', '#NUM!', '#REF!', '#VALUE!', '#SPILL!']
                    Only applied if as_df is True.
                chunk_size: Optional Chunk size in # of cells. Used to handle read requests that are too large.
                **kwargs: Optional kwargs that can be passed in to pandas read_csv.
        """
        # Get the range address, so we can chunk up the read action
        address, rows, cols = self.get_used_range_info(sheet_name, range_address=range_address)
        address = address.split('!')[-1]

        # Calculate the row chunk size, and read the data in chunks
        row_chunk_size = chunk_size // cols
        data = []
        for i in range(0, rows, row_chunk_size):
            ul = xl_shift_cell(address, row_shift=i)
            br = xl_shift_cell(address, row_shift=min(i + row_chunk_size - 1, rows - 1), col_shift=cols - 1)
            data += self.get(f"/worksheets/{sheet_name}/range(address='{ul}:{br}')?$select=text").get('text')

        if as_df:
            # Replace errors/empties with NaNs
            default_errors = ['', '#DIV/0!', '#N/A', '#NAME?', '#NULL!', '#NUM!', '#REF!', '#VALUE!', '#SPILL!']
            nan_errors = default_errors if nan_errors is None else nan_errors

            # Convert to CSV string and feed to Pandas. Excel weirdly pads with whitespace...
            data = '\n'.join(['\x1f'.join([i.strip() for i in row]) for row in data])
            return pd.read_csv(StringIO(data), sep='\x1f', na_values=nan_errors, **kwargs)
        else:
            return [[i.strip() for i in row] for row in data]

    def clear_range(self, sheet_name, range_address=None, apply_to='All'):
        """
            Clear the data on a given sheet, with the option of clearing only a specific range.
            If the range is not given, the full sheet will be cleared.

            Args:
                sheet_name: Name of the desired sheet.
                range_address: Optional string with the Range address (A1 format).
                apply_to: Type of clear. Must be in ['All', 'Format', 'Contents'].
        """
        if range_address is None:
            url = f"/worksheets/{sheet_name}/usedRange/clear"
        else:
            url = f"/worksheets/{sheet_name}/range(address='{range_address}')/usedRange/clear"
        self.post(url, json={'applyTo': apply_to})

    def delete_range(self, sheet_name, range_address=None, shift='Up'):
        """
            Delete the data on a given sheet, with the option of deleting only a specific range.
            If the range is not given, the full sheet will be deleted.

            Args:
                sheet_name: Name of the desired sheet.
                range_address: Optional string with the Range address (A1 format).
                shift: How to shift remaining ranges. Must be in ['Up', 'Left'].
        """
        if range_address is None:
            url = f"/worksheets/{sheet_name}/usedRange/delete"
        else:
            url = f"/worksheets/{sheet_name}/range(address='{range_address}')/usedRange/delete"
        self.post(url, json={'shift': shift})

    def write_value(self, sheet_name, range_address, value):
        """
            Write one value to a cell/range. Creates the sheet first if the sheet does not exist.

            Args:
                sheet_name: Name of the desired sheet.
                range_address: String with the Cell/Range address (A1 format).
                value: Value to write to the cell.
        """
        self.create_sheet(sheet_name)
        url = f"/worksheets/{sheet_name}/range(address='{range_address}')"
        self.patch(url, json={'values': value})

    def write_data(self, sheet_name, df, location='A1', include_header=True, chunk_size=250000, ignore_timeout=False):
        """
            Write a DataFrame to a sheet. Can select location if desired, default is A1.
            Please note that large DataFrames will be uploaded in chunks of 250,000 cells by default.
            Depending on the data types of your data, you may need to select a custom chunk-size to avoid
            API size limit errors.

            Args:
                sheet_name: Name of the desired sheet.
                df: Pandas DataFrame with input data to write.
                location: Address of the Upper Left square of the target Range for the data. Default is A1.
                include_header: Optional Boolean indicating whether the DataFrame's header should be written.
                chunk_size: Optional Chunk size in # of cells. Used to handle write requests that are too large.
                ignore_timeout: Optional Boolean to ignore timeouts. Sometimes Microsoft's API times out unexpectedly.
        """
        self.create_sheet(sheet_name)

        # Convert the DataFrame to a list of lists, count columns.
        data = df.replace([np.inf, -np.inf], '=1/0').fillna('').values.tolist()
        _, cols = df.shape
        if include_header:
            data = [df.columns.values.tolist()] + data

        # Generator for the chunks of data to upload, including the starting address for each
        def get_chunk(lst, n):
            """ Yield successive chunks from the data list. """
            for i in range(0, len(lst), n):
                yield lst[i:i + n], xl_shift_cell(location, row_shift=i)

        # Loop through the chunks and write them
        row_chunk_size = chunk_size // cols
        for chunk, chunk_start in get_chunk(data, row_chunk_size):
            # Get the exact range for the chunk
            chunk_end = xl_shift_cell(chunk_start, row_shift=min(row_chunk_size, len(chunk)) - 1, col_shift=cols - 1)
            range_address = f'{chunk_start}:{chunk_end}'

            # Update the range
            url = f"/worksheets/{sheet_name}/range(address='{range_address}')"
            self.patch(url, json={'values': chunk}, ignore_timeout=ignore_timeout)

    def append_data(self, sheet_name, df, first_column='A', include_header=False,
                    chunk_size=250000, ignore_timeout=False):
        """
            Append a DataFrame to a sheet. Can select a specific first column if desired, default is Column A.
            This method will try to automatically detect the endpoint of the existing data, and append from there.
            Please note that large DataFrames will be uploaded in chunks of 250,000 cells by default.
            Depending on the data types of your data, you may need to select a custom chunk-size to avoid
            API size limit errors.

            Args:
                sheet_name: Name of the desired sheet.
                df: Pandas DataFrame with input data to write.
                first_column: First column of the target Range for the data. Default is A.
                include_header: Optional Boolean indicating whether the DataFrame's header should be written.
                chunk_size: Optional Chunk size in # of cells. Used to handle write requests that are too large.
                ignore_timeout: Optional Boolean to ignore timeouts. Sometimes Microsoft's API times out unexpectedly.
        """
        self.create_sheet(sheet_name)

        # Get current used range, and set the new location as the next row
        try:
            url = f"/worksheets/{sheet_name}/range(address='{first_column}:{first_column}')" \
                  f"/usedRange(valuesOnly=true)/Lastcell?$select=address"
            used_address = self.get(url).get('address').split('!')[1]
            new_loc = xl_shift_cell(used_address, row_shift=1)
        except ValueError:
            new_loc = first_column + '1'
            include_header = True

        self.write_data(sheet_name, df, location=new_loc, include_header=include_header, chunk_size=chunk_size,
                        ignore_timeout=ignore_timeout)

    def read_csv(self, **kwargs):
        """
            All WorkbookClient methods only work on .xlsx files.
            We provide this read_csv method to allow users to at least read .csv files.

            Args:
                **kwargs: Optional kwargs that can be passed in to pandas read_csv.
        """
        url = f'/drives/{self.drive_id}/items/{self.item_id}/content'
        res = self.client.get(url)

        if 'xml' in res.headers.get('Content-Type', ''):
            raise ValueError('read_csv only works for CSV files!')

        return pd.read_csv(StringIO(res.text), **kwargs)

    def save_as(self, new_name=None, destination=None, drive_root='/me/drive/root'):
        """
            Save a copy of the Excel Workbook to OneDrive.
            If a new destination folder is not specified, then a copy will be saved in the same folder.
            Name conflicts will automatically be renamed.

            Args:
                new_name: Optional String specifying a new name. If no extension provided, .xlsx is assumed.
                destination: Optional String specifying the Folder to which the file will be saved.
                drive_root: Optional String specifying the Drive to which the Folder will be located.
        """
        body = {'@microsoft.graph.conflictBehavior': 'rename'}

        if new_name is not None:
            body['name'] = new_name if new_name.endswith('.xlsx') or new_name.endswith('.csv') else new_name + '.xlsx'

        if destination is not None:
            dc = DriveClient(self.config)
            _, drive_id, item_id = dc.get_folder(destination, drive_root=drive_root)
            body['parentReference'] = {'driveId': drive_id, 'id': item_id}

        self.client.post(f'/drives/{self.drive_id}/items/{self.item_id}/copy', json=body)

    def share_with_org(self, access_type='view'):
        """
            Grant access to the entire organization. Users who navigate to the Excel file will be granted
            the desired access (either 'edit' or 'view', default is 'view').

            This method returns a Share URL which can be distributed if needed.

            Args:
                access_type: String ['edit', 'view'] indicating access type. Default is 'view'.
        """
        assert access_type in ['edit', 'view'], "Access type must be 'edit' or 'view'"
        body = {'type': access_type, 'scope': 'organization'}
        res = self.client.post(f'/drives/{self.drive_id}/items/{self.item_id}/createLink', json=body)
        return res.json()['link']['webUrl']

    def share_with_users(self, user_list, access_type='view', send_email=False):
        """
            Grant access to a specific set of users. Users who navigate to the Excel file will be granted
            the desired access (either 'edit' or 'view', default is 'view').

            This method does not return a Share URL. Instead, you can set send_email to True
            to send an email with the invitation and share link.

            Args:
                user_list: List of user email addresses to grant permission.
                access_type: String ['edit', 'view'] indicating access type. Default is 'view'.
                send_email: Optional Boolean, send email to users with invitations to the sheet (Default False).
        """
        if isinstance(user_list, str):
            user_list = [user_list]
        assert isinstance(user_list, list), 'User list must be a list'
        assert access_type in ['edit', 'view'], "Access type must be 'edit' or 'view'"

        role = 'read' if access_type == 'view' else 'write'     # Invite API uses different terminology
        body = {
            'roles': [role],
            'recipients': [{'email': u} for u in user_list],
            'sendInvitation': send_email,
            'requireSignIn': True,
        }
        self.client.post(f'/drives/{self.drive_id}/items/{self.item_id}/invite', json=body)

    def increment_column(self,column):
        if not column:
            return 'A'
        if column[-1] == 'Z':
            return self.increment_column(column[:-2]) + 'A'
        return column[:-1] + chr(ord(column[-1]) + 1) if column else 'A'

    def loop_write(self, sheet_name, df, location='A1', include_header=True, chunk_size=250000, ignore_timeout=False):
        """
            Write a DataFrame to a sheet in a column wise loop to avoid failures. Can select location if desired, default is A1.
            Please note that large DataFrames will be uploaded in chunks of 250,000 cells by default.
            Depending on the data types of your data, you may need to select a custom chunk-size to avoid
            API size limit errors.

            Args:
                sheet_name: Name of the desired sheet.
                df: Pandas DataFrame with input data to write.
                location: Address of the Upper Left square of the target Range for the data. Default is A1.
                include_header: Optional Boolean indicating whether the DataFrame's header should be written.
                chunk_size: Optional Chunk size in # of cells. Used to handle write requests that are too large.
                ignore_timeout: Optional Boolean to ignore timeouts. Sometimes Microsoft's API times out unexpectedly.
        """
        for i in df.columns:
            location = location  # Set the current location
            values=df[[i]]
            self.write_data(sheet_name, values, location=location,include_header=include_header,chunk_size=chunk_size,ignore_timeout=ignore_timeout)
            location = self.increment_column(location[:-1]) + location[-1]


class SpreadsheetClient:
    """
        Optional Spreadsheet Client if the user prefers to have an object to manage one sheet,
        rather than constantly passing the sheet name in to all of the WorkbookClient methods.

        Only contains sheet-based methods; this class basically wraps the WorkbookClient methods.

        Acquire a Spreadsheet Client using the `get_sheet` method of a Workbook Client:
        > wb_client = WorkbookClient(share_url)

        > ss_client = wb_client.get_sheet(sheet_name)
    """
    def __init__(self, sheet_name, workbook_client: WorkbookClient):
        self.name = sheet_name
        self.wc = workbook_client

        # At this point, create the sheet if it does not exist
        self.wc.create_sheet(self.name)

    def get_used_range_info(self, range_address=None):
        """
            Extract the Used Range information, from an optional range address if desired,
            namely the address, number of rows, and number of columns.
            Returns a tuple: (address, rows, cols)

            Args:
                range_address: Optional string with the Range address (A1 format).
        """
        return self.wc.get_used_range_info(self.name, range_address=range_address)

    def get_range_data(self, range_address=None, as_df=True, nan_errors=None, chunk_size=500000, **kwargs):
        """
        Read the data from a given range, provided an optional Range Address.

        Args:
            range_address: Optional string with the Range address (A1 format).
            as_df: Optional Boolean deciding if the results are desired as a DataFrame.
            nan_errors: Optional List of Excel errors to explicitly replace as NaN. Otherwise, defaults to:
                ['#DIV/0!', '#N/A', '#NAME?', '#NULL!', '#NUM!', '#REF!', '#VALUE!', '#SPILL!']
                Only applied if as_df is True.
            chunk_size: Optional Chunk size in # of cells. Used to handle read requests that are too large.
            **kwargs: Optional kwargs that can be passed in to pandas read_csv.
        """
        return self.wc.get_range_data(self.name, range_address=range_address, as_df=as_df,
                                      nan_errors=nan_errors, chunk_size=chunk_size, **kwargs)

    def clear_range(self, range_address=None, apply_to='All'):
        """
            Clear the data on the sheet, with the option of clearing only a specific range.
            If the range is not given, the full sheet will be cleared.

            Args:
                range_address: Optional string with the Range address (A1 format).
                apply_to: Type of clear. Must be in ['All', 'Format', 'Contents'].
        """
        self.wc.clear_range(self.name, range_address=range_address, apply_to=apply_to)

    def delete_range(self, range_address, shift='Up'):
        """
            Delete the data on the sheet, with the option of deleting only a specific range.
            If the range is not given, the full sheet will be deleted.

            Args:
                range_address: Optional string with the Range address (A1 format).
                shift: How to shift remaining ranges. Must be in ['Up', 'Left'].
        """
        self.wc.delete_range(self.name, range_address=range_address, shift=shift)

    def write_value(self, range_address, value):
        """
            Write one value to a cell/range.

            Args:
                range_address: String with the Cell/Range address (A1 format).
                value: Value to write to the cell.
        """
        self.wc.write_value(self.name, range_address, value)

    def write_data(self, df, location='A1', include_header=True, chunk_size=250000, ignore_timeout=False):
        """
            Write a DataFrame to a sheet. Can select location if desired, default is A1.
            Please note that large DataFrames will be uploaded in chunks of 250,000 cells by default.
            Depending on the data types of your data, you may need to select a custom chunk-size to avoid
            API size limit errors.

            Args:
                df: Pandas DataFrame with input data to write.
                location: Address of the Upper Left square of the target Range for the data. Default is A1.
                include_header: Optional Boolean indicating whether the DataFrame's header should be written.
                chunk_size: Optional Chunk size in # of cells. Used to handle read requests that are too large.
                ignore_timeout: Optional Boolean to ignore timeouts. Sometimes Microsoft's API times out unexpectedly.
        """
        self.wc.write_data(self.name, df, location=location, include_header=include_header, chunk_size=chunk_size,
                           ignore_timeout=ignore_timeout)

    def append_data(self, df, first_column='A', include_header=False, chunk_size=250000, ignore_timeout=False):
        """
            Append a DataFrame to a sheet. Can select a specific first column if desired, default is Column A.
            This method will try to automatically detect the endpoint of the existing data, and append from there.
            Please note that large DataFrames will be uploaded in chunks of 250,000 cells by default.
            Depending on the data types of your data, you may need to select a custom chunk-size to avoid
            API size limit errors.

            Args:
                df: Pandas DataFrame with input data to write.
                first_column: First column of the target Range for the data. Default is A1.
                include_header: Optional Boolean indicating whether the DataFrame's header should be written.
                chunk_size: Optional Chunk size in # of cells. Used to handle read requests that are too large.
                ignore_timeout: Optional Boolean to ignore timeouts. Sometimes Microsoft's API times out unexpectedly.
        """
        self.wc.append_data(self.name, df, first_column=first_column,
                            include_header=include_header, chunk_size=chunk_size, ignore_timeout=ignore_timeout)
