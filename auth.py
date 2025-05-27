"""
    Authorization classes to acquire an Auth Token for the User via the Device Code Flow protocol:
    https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-device-code

    Auth/Refresh Tokens can be cached locally if desired by the user, but to do so, the user must ensure
    that a local file storage will persist, for example running locally or on a persistent VM.

    For applications that will be running on non-persistent resources (i.e. spot VMs, clusters),
    we enable usage of an Azure Blob to store the Token Cache. Accessing the Blob will require
    either Azure CLI login if being used locally, or Managed Identity login if being used on an Azure VM.
"""


import os
import msal
import time
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobClient
from appdirs import user_data_dir


APP_NAME = 'PY_OYOMS'
AZURE_TOKEN_CONTAINER = 'https://stephenlee.blob.core.windows.net/tokens'
SIGN_IN_TIMEOUT = 300   # Give the user a time limit (seconds) to sign in. This will ensure unattended scripts fail.
AZURE_ID_REF = {
    'OYO': {
        'tenant_id': '04ec3963-dddc-45fb-afb7-85fa38e19b99',
        'app_id': '7c8cca7c-7351-4d57-b94d-18e2ba1e4e24',    # Tied to Application OYO-Python and R
    },
    'OVH': {
        'tenant_id': 'ad0a533f-0117-494e-93f1-1ba98a9fd13c',
        'app_id': 'd7aad037-aacb-47e8-9953-3fd6c906216e'
    },
}


class AuthConfig:
    """
        Small class to wrap the dictionary that dictates how and where to store the Auth Tokens.
        Sets the default Local config cache.
    """
    def __init__(self, user, style='local', path=None, cache_name='py_token_cache.bin', tenant='OYO', client_id=None):
        """
            Constructor method. All inputs will default to a Local, App directory.

            Args:
                user: User to whom the config will be assigned.
                style: Must be either 'local' or 'blob', dictating where to cache the config.
                path: If style is 'local', this provides the directory where the cache gets stored.
                cache_name: Name suffix of the config file itself. Defaults to 'py_token_cache.bin'.
                tenant: String specifying the Tenant. Current options are: ['OYO', 'OVH']
                client_id: String containing the Azure Application ID for the App requesting tokens.
        """
        assert style in ['local', 'blob'], "AuthConfig style must either be 'local' or 'blob'."
        assert tenant in AZURE_ID_REF, f"Tenant must be in {list(AZURE_ID_REF.keys())}"

        self.user = user
        self.style = style
        self.path = user_data_dir(APP_NAME) if path is None else path
        self.cache_name = cache_name
        self.tenant = tenant
        self.client_id = AZURE_ID_REF.get(self.tenant).get('app_id') if client_id is None else client_id

        # Create the local config directory if needed
        if self.is_local() and not os.path.exists(self.path):
            os.makedirs(self.path)

    def is_local(self):
        """
            Boolean sharing whether or not the AuthConfig is local or not.
        """
        return self.style == 'local'


class DeviceCodeFlowCredential:
    """
        Authentication Flow to enable browser-less deployment. User will be given a link to submit to
        a browser on an (optionally) separate device.

        Based on the following sample:
        https://github.com/AzureAD/microsoft-authentication-library-for-python/blob/dev/sample/device_flow_sample.py

        Uses a Token Cache Serialization strategy suggested here:
        https://msal-python.readthedocs.io/en/latest/#msal.SerializableTokenCache
    """

    def __init__(self, config: AuthConfig):
        self.config = config

        # Set up the Token Cache
        self.cache = msal.SerializableTokenCache()

        # Read Token Cache from memory
        if self.config.is_local():
            self._read_local_cache()
        else:
            self._read_cloud_cache()

        # Instantiate the application which will obtain Auth Tokens
        self.app = msal.PublicClientApplication(
            self.config.client_id,
            authority='https://login.microsoftonline.com/' + AZURE_ID_REF.get(self.config.tenant).get('tenant_id'),
            token_cache=self.cache,
        )

    def get_token(self, *scopes):
        """
            This method is named get_token to satisfy the Abstract Method requirements of the TokenCredential
            class from the msgraph.core package.

            Searches the cached application for the given username, and then applies for a config.
            If the request is rejected, then the user is asked to authenticate manually.
        """
        result = None

        # Extract the specified user from the cache file
        my_user = [i for i in self.app.get_accounts() if i.get('username') == self.config.user]
        scope_list = list(scopes) if scopes else ['.default']
        if my_user:
            result = self.app.acquire_token_silent(scope_list, account=my_user[0])

        # If we are unable to acquire a config silently, we need to ask the user to authenticate
        if not result:
            flow = self.app.initiate_device_flow(scopes=scope_list)
            print(flow.get('message', 'Flow failed...'))

            deadline = int(time.time()) + SIGN_IN_TIMEOUT
            result = self.app.acquire_token_by_device_flow(flow, exit_condition=lambda x: time.time() > deadline)

            if 'access_token' not in result:
                raise KeyError(f'Device Code Flow Authentication Failed or Timed Out ({SIGN_IN_TIMEOUT} Second Limit).')

        # If the cache has been updated, re-write it now
        if self.cache.has_state_changed:
            if self.config.is_local():
                self._write_local_cache()
            else:
                self._write_cloud_cache()

        return [result.get('access_token')]

    def _local_cache_path(self):
        """
            Define the local cache path.
        """
        cache_file = self.config.user.split('@')[0] + '_' + self.config.cache_name
        return os.path.abspath(os.path.join(self.config.path, cache_file))

    def _read_local_cache(self):
        """
            Read a local config cache.
        """
        cache_path = self._local_cache_path()
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as f:
                self.cache.deserialize(f.read())

    def _write_local_cache(self):
        """
            Write a local config cache.
        """
        with open(self._local_cache_path(), 'w') as f:
            f.write(self.cache.serialize())

    def _cloud_cache_path(self):
        """
            Define the cloud cache path.
        """
        cache_path = AZURE_TOKEN_CONTAINER + '/' + self.config.user.split('@')[0] + '/' + self.config.cache_name
        return BlobClient.from_blob_url(blob_url=cache_path, credential=DefaultAzureCredential())

    def _read_cloud_cache(self):
        """
            Read an Azure Blob config cache.
        """
        cache_blob = self._cloud_cache_path()
        if cache_blob.exists():
            self.cache.deserialize(cache_blob.download_blob().readall())

    def _write_cloud_cache(self):
        """
            Write an Azure Blob config cache.
            By default, a folder in the Container will be created under the User's ID, in which the
            config cache will then be stored.
        """
        cache_blob = self._cloud_cache_path()
        cache_blob.upload_blob(self.cache.serialize(), overwrite=True)
