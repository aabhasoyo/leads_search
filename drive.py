"""
    Client designed to interact with Microsoft OneDrive.
"""


from .core import CoreClient
from .misc import get_drive_item_ids
from pathlib import Path
import requests
import io
from tempfile import NamedTemporaryFile
from openpyxl import Workbook


UPLOAD_LIMIT = 1024 * 1024 * 4  # 4 MB Simple Upload limit
DEFAULT_CHUNK_SIZE = 1024 * 1024 * 5  # 5 MB Default Chunk Size


class DriveClient(CoreClient):
    """
        Constructs a custom HTTPClient to be used for requests against OneDrive.

        This Client will act on behalf of an Azure User via an application registered through Azure AD.
    """

    def __init__(self, config, **kwargs):
        """
            Class constructor that accepts a User Email Address to log in to OneDrive.

            Args:
                config: An AuthConfig object configuring the Token Cache, or the username string.
        """

        # Super class sets up the resource path, so we collect credentials then run super init.
        super().__init__(config, scopes=['Files.ReadWrite.All'], **kwargs)


    def upload_file(self, file, stream=None, target_path=None,
                    chunk_size=DEFAULT_CHUNK_SIZE, drive_root='/me/drive/root'):
        """
            Upload a file to OneDrive. If the file exceeds 4MB, the upload automatically gets split into chunks.
            https://docs.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0&tabs=http
            https://docs.microsoft.com/en-us/graph/api/driveitem-createuploadsession?view=graph-rest-1.0

            Args:
                file: File for upload. Must be a string path to a local file.
                stream: Optional alternative to a file upload: a file stream object. In this case, the file
                    input is used to infer a filename.
                target_path: Optional Address on the OneDrive to write the file. Can be a path to the desired folder,
                    in which case the path should end with a forward slash - '/FolderA/FolderB/'; or can be a path
                    with a custom filename - '/FolderA/FolderB/FileName.txt'. Default write is to the root folder with
                    the same file name.
                chunk_size: Optional chunk upload size in bytes. Only used if file exceeds 4MB. Must be a
                    multiple of 327,680 bytes (320 KB)
                drive_root: Optional String specifying a custom drive root directory. Default is /me/drive/root
        """
        # Get file and its size
        file = Path(file)
        if stream is not None:
            file_size = stream.seek(0, 2)           # Navigate to end of stream to get the size
            stream.seek(0)                          # Navigate back to start, for reading later
        else:
            file_size = file.stat().st_size

        # Default target is root path. If input ends with /, then assume user wants to load to a folder.
        if target_path is None:
            target_path = Path(file.name)
        elif target_path.endswith('/'):
            target_path = Path(target_path) / file.name
        else:
            target_path = Path(target_path)

        # URL Prefix for both simple and long uploads
        parent_url, _, _ = self.get_folder(str(target_path.parent), drive_root=drive_root)
        url_prefix = parent_url + f':/{target_path.name}'

        if file_size <= UPLOAD_LIMIT:
            # Simple File Upload
            if stream is None:
                with file.open(mode='rb') as f:
                    data = f.read()
            else:
                data = stream.read()

            simple_url = url_prefix + ':/content'
            headers = {'Content-type': 'application/octet-stream'}
            return self.put(simple_url, headers=headers, data=data)
        else:
            # Chunk Upload - need to open a session and upload in chunks
            headers = {'Content-Type': 'application/json'}
            session_url = self.post(url_prefix + ':/createUploadSession', headers=headers).get('uploadUrl')

            def chunk_upload(ff):
                current_bytes = 0
                while True:
                    # Read a chunk, exit when data upload is done
                    chunk = ff.read(chunk_size)
                    if not chunk:
                        break

                    # Compile the header to track progress
                    transfer_bytes = len(chunk)
                    chunk_headers = {
                        'Content-Length': str(transfer_bytes),
                        'Content-Range': f'bytes {current_bytes}-{current_bytes + transfer_bytes - 1}/{file_size}'
                    }
                    current_bytes += transfer_bytes

                    # Upload the chunk
                    res = requests.put(session_url, data=chunk, headers=chunk_headers)

                    # Check for errors, break if done
                    res.raise_for_status()
                    if res.status_code != 202:
                        return res.json()

            if stream is None:
                with file.open(mode='rb') as f:
                    chunk_upload(f)
            else:
                chunk_upload(stream)


    def get_folder(self, path, drive_root='/me/drive/root'):
        """
            Retrieve the Drive ID and Item ID of a folder using its folder path (and optionally a drive root).
            Create the folder paths if necessary.

            Args:
                path: String with a path to the folder. Use forward slashes.
                drive_root: Optional String if your drive root is somewhere other than your user root.
        """
        path_chain = Path(path.strip('/')).parts

        # Start by getting the root
        folder, folder_drive_id, folder_item_id = get_drive_item_ids(self.get(drive_root))

        # Loop through the chain and try to Get. If Get fails, then Create.
        for name in path_chain:
            try:
                folder, folder_drive_id, folder_item_id = get_drive_item_ids(self.get(f'{folder}:/{name}'))
            except:
                body = {'name': name, 'folder': {}, '@microsoft.graph.conflictBehavior': 'fail'}
                folder, folder_drive_id, folder_item_id = get_drive_item_ids(self.post(f'{folder}/children', json=body))

        return folder, folder_drive_id, folder_item_id


    def get_item(self, path, drive_root='/me/drive/root'):
        """
            Take a OneDrive file path and retrieve the Drive Item information.
            Will raise error if Item does not exist.

            Args:
                path: String with the file path.
                drive_root: Optional String if your drive root is somewhere other than your user root.
        """
        return self.get(f"{drive_root}:/{path.strip('/')}")


    def df_to_csv(self, df, target_path, **kwargs):
        """
            Take a Pandas DataFrame and write it to a CSV on OneDrive.
            Returns a DriveItem dictionary with metadata on the written file.

            Args:
                df: Pandas DataFrame to write to CSV
                target_path: Address on the OneDrive to write the CSV. Separate folders with forward slashes,
                    for example "/Storage/Folder/data.csv". If only a CSV name is provided, then it will
                    be written to the User's default Drive.
                **kwargs: Same optional args that can be provided to pandas.DataFrame.to_csv
        """
        stream = io.StringIO()
        df.to_csv(stream, **kwargs)

        target_path = Path(target_path)
        name = target_path.name if target_path.name.endswith('.csv') else target_path.name + '.csv'
        parent = None if target_path.parent in ['.', '/'] else str(target_path.parent) + '/'
        return self.upload_file(name, stream=stream, target_path=parent)


    def df_to_xlsx(self, df, target_path, **kwargs):
        """
            Take a Pandas DataFrame and write it to an XLSX on OneDrive.
            Returns a DriveItem dictionary with metadata on the written file.

            Args:
                df: Pandas DataFrame to write to XLSX
                target_path: Address on the OneDrive to write the XLSX. Separate folders with forward slashes,
                    for example "/Storage/Folder/data.csv". If only a XLSX name is provided, then it will
                    be written to the User's default Drive.
                **kwargs: Same optional args that can be provided to pandas.DataFrame.to_excel
        """
        # Create an empty workbook, then dump the df
        wb = Workbook()
        with NamedTemporaryFile() as tmp:
            wb.save(tmp.name)
            df.to_excel(tmp, **kwargs)
            tmp.seek(0)

            # Upload the xlsx to OneDrive
            target_path = Path(target_path)
            name = target_path.name if target_path.name.endswith('.xlsx') else target_path.name + '.xlsx'
            parent = None if target_path.parent in ['.', '/'] else str(target_path.parent) + '/'
            return self.upload_file(name, stream=tmp, target_path=parent)
