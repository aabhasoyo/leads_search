"""
    Core client class for interaction with the Microsoft Graph API.
"""


from msgraph.core import GraphClient
from .auth import DeviceCodeFlowCredential, AuthConfig
import json
import pandas as pd
import datetime


class CoreClient:
    """
        Constructs a custom HTTPClient to be used for requests against the Microsoft Graph API
        for a specific type of resource.

        This Client will act on behalf of an Azure User via an application registered through Azure AD.
    """

    def __init__(self, config, **kwargs):
        """
            Class constructor. Instantiates the GraphClient with credentials.

            Args:
                config: An AuthConfig object configuring the Token Cache, or the username string.
        """
        assert isinstance(config, str) or isinstance(config, AuthConfig), 'config must be str or AuthConfig.'

        # Default config is Local
        if isinstance(config, str):
            config = AuthConfig(user=config)
        self.config = config

        # Awful hack due to GraphClient caching instances...Need to retrieve scopes from existing GraphClient.
        if GraphClient._GraphClient__instance is not None and 'scopes' in kwargs:
            old = GraphClient._GraphClient__instance.graph_session.adapters.get('https://')._first_middleware.scopes
            kwargs['scopes'] = list(set(kwargs['scopes'] + old))

        # Instantiate the client through which all API calls will be made
        credential = DeviceCodeFlowCredential(config=self.config)
        self.client = GraphClient(credential=credential, **kwargs)

        # Set a custom resource path if desired
        self.resource_path = ''
        self._custom_resource_path()


    def _custom_resource_path(self):
        """
            Set up a custom root resource path for your instantiation of the Client.
            Useful to help make subsequent API calls look cleaner.
        """
        pass

    def _request(self, request_type, request_path, as_json=True, **kwargs):
        """
            Generic method to perform a request of any type via the client.

            Args:
                request_type: Must be in ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
                request_path: Must begin with "/"
                **kwargs: Optional arguments accepted by the requests methods.
        """
        # Add the default resource path
        path = self.resource_path + request_path

        # If the JSON field is passed in, transfer it to the data arg with our custom encoder
        req_json = kwargs.pop('json', None)
        if req_json:
            kwargs['data'] = json.dumps(req_json, cls=CoreJSONEncoder)
            kwargs['headers'] = {**{'Content-Type': 'application/json'}, **kwargs.pop('headers', {})}

        # Pop this flag before request
        ignore_timeout = kwargs.pop('ignore_timeout', False)

        # Execute the request
        res = self._custom_request(request_type, path, **kwargs)

        # Option to ignore 504 status code
        if not (ignore_timeout and res.status_code == 504):
            # Raise error if HTTP request returns an unsuccessful status code, with custom errors if they exist
            if 'application/json' in res.headers.get('Content-Type', '') and res.json().get('error'):
                code = res.json().get('error', {}).get('code')
                msg = res.json().get('error', {}).get('message')
                raise ValueError(f'{code}: {msg}')
            res.raise_for_status()

        # Return JSON if requested and valid
        if as_json and 'application/json' in res.headers.get('Content-Type', ''):
            return res.json()
        else:
            return res

    def _custom_request(self, request_type, path, **kwargs):
        """
            Allows override for the request behavior. Default behavior is a standard single request.
        """
        return getattr(self.client, request_type)(path, **kwargs)

    def get(self, path, **kwargs):
        """
            Sends a GET request.

            Args:
                path: API Path starting with "/", following the resource relationship.
                kwargs: Optional arguments accepted by the requests methods.
        """
        return self._request('get', path, **kwargs)

    def put(self, path, **kwargs):
        """
            Sends a PUT request.

            Args:
                path: API Path starting with "/", following the resource relationship.
                kwargs: Optional arguments accepted by the requests methods.
        """
        return self._request('put', path, **kwargs)

    def post(self, path, **kwargs):
        """
            Sends a POST request.

            Args:
                path: API Path starting with "/", following the resource relationship.
                kwargs: Optional arguments accepted by the requests methods.
        """
        return self._request('post', path, **kwargs)

    def patch(self, path, **kwargs):
        """
            Sends a PATCH request.

            Args:
                path: API Path starting with "/", following the resource relationship.
                kwargs: Optional arguments accepted by the requests methods.
        """
        return self._request('patch', path, **kwargs)

    def delete(self, path, **kwargs):
        """
            Sends a DELETE request.

            Args:
                path: API Path starting with "/", following the resource relationship.
                kwargs: Optional arguments accepted by the requests methods.
        """
        return self._request('delete', path, **kwargs)


class CoreJSONEncoder(json.JSONEncoder):
    """
        Set up package-wide JSON Encoding for interaction with the Graph API.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def default(self, o):
        if isinstance(o, pd.Timestamp):
            if o.hour + o.minute + o.second + o.microsecond:     # Detect a non-date Timestamp
                return o.strftime('%Y-%m-%d %H:%M:%S')
            else:
                return o.strftime('%Y-%m-%d')

        if isinstance(o, datetime.date):
            return o.strftime("%Y-%m-%d")

        if isinstance(o, datetime.datetime):
            return o.strftime('%Y-%m-%d %H:%M:%S')

        return json.JSONEncoder.default(self, o)
