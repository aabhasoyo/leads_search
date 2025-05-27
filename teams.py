"""
    Client designed to interact with Microsoft Teams.
"""


from .core import CoreClient
from .drive import DriveClient
from .excel import WorkbookClient
import re
import base64
from PIL import Image
from urllib.parse import unquote


class TeamsClient(CoreClient):
    """
        Constructs a custom HTTPClient to be used for requests against Microsoft Teams.

        This Client will act on behalf of an Azure User via an application registered through Azure AD.
    """

    def __init__(self, config, **kwargs):
        """
            Class constructor that accepts a User Email Address to log in to Teams.

            Args:
                config: An AuthConfig object configuring the Token Cache, or the username string.
        """

        # Super class sets up the resource path, so we collect credentials then run super init.
        super().__init__(config, scopes=['ChannelMessage.Send', 'Chat.ReadWrite', 'User.ReadBasic.All'], **kwargs)

    def send_message(self, message, chat_id=None, channel_url=None, images=None, attachments=None):
        """
            Send a message to a Teams Channel or Chat.
            Reference: https://docs.microsoft.com/en-us/graph/api/chatmessage-post?view=graph-rest-1.0&tabs=http

            You must provide either a Chat ID or a Channel URL. To find a Chat ID, try using the
            TeamsClient.get_chat_list function. To find a Channel URL, click ... next to the Channel name and select
            "Get link to channel". If the Channel only provides the "Get email address" option, then you can instead
            use the OutlookClient to send an email to the channel.

            Images and attachments must be locally stored, and supplied as a list of local file path strings.
            Images will be shown in the body of the message, at the end.

            You can tag users in the message itself by using the pattern $TAG(user@oyorooms.com).

            Args:
                message: String containing the message to send to the channel. Interpreted as HTML string.
                chat_id: Optional string with the Chat ID number.
                channel_url: Optional string with the Channel URL.
                images: Optional list of local file paths to images to include in the message.
                attachments: Optional list of local file paths to attachments to include in the message.
        """
        if chat_id is None and channel_url is None:
            raise ValueError('Must provide either chat_id or channel_url!')

        if chat_id is not None and channel_url is not None:
            raise ValueError('Only provide a chat_id or a channel_url!')

        # Get the URLs
        if chat_id:
            url = f'/chats/{chat_id}/messages'
            channel_id = ''
        else:
            channel_id = re.search('channel/(.*)/', channel_url).group(1)
            team_id = re.search('groupId=(.*)&', channel_url).group(1)
            url = f'/teams/{team_id}/channels/{channel_id}/messages'

        # Message body by default is just the message
        body = message

        # Parse and replace user tagging, identified by $TAG(username@oyorooms.com).
        tags = re.findall(r'\$TAG\(.+?\)', body)
        mentions = []
        if tags:
            for idx, tag in enumerate(tags):
                user = tag[5: -1]

                # Either tag the channel, or search for a user email
                if user.lower() == 'channel' and channel_id:
                    user_name = 'Here'
                    mention_dict = {
                        'conversation': {
                            'displayName': user_name,
                            'id': unquote(channel_id),
                            'conversationIdentityType': 'channel',
                        }
                    }
                else:
                    try:
                        user_info = self.get(f"/users('{user}')?$select=id,displayName")
                    except ValueError:
                        continue

                    user_id, user_name = list(map(user_info.get, ['id', 'displayName']))
                    mention_dict = {
                        'user': {
                            'displayName': user_name,
                            'id': user_id,
                            'userIdentityType': 'aadUser',
                        }
                    }

                mentions.append({
                    'id': idx,
                    'mentionText': user_name,
                    'mentioned': mention_dict
                })
                body = body.replace(tag, f'<at id=\"{idx}\">{user_name}</at>')

        # Attach images if possible
        hosted_content = []
        images = [] if images is None else images
        if isinstance(images, str):
            images = [images]
        for idx, path in enumerate(images):
            # Images need to be base64 encoded
            with open(path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Get image size
            with Image.open(path) as im:
                width, height = im.size

            body += f'<br><span><img src="../hostedContents/{idx}/$value" height="{height}" width="{width}"></span>'
            hosted_content.append({
                "@microsoft.graph.temporaryId": str(idx),
                "contentBytes": image_base64,
                "contentType": "image/png",
            })

        # Provide attachments if desired.
        attach_list = []
        attachments = [] if attachments is None else attachments
        if isinstance(attachments, str) or isinstance(attachments, WorkbookClient):
            attachments = [attachments]
        if attachments:
            dc = DriveClient(self.config)      # Create a DriveClient to use for attachment uploads

            # Get the drive location for file uploads (only for channels; for chats, use user root default)
            params = {'target_path': 'OYOMS Uploads/'}
            if channel_url:
                res = self.get(f'/teams/{team_id}/channels/{channel_id}/filesFolder')
                params['drive_root'] = f"/drives/{res.get('parentReference').get('driveId')}/items/{res.get('id')}"

            for item in attachments:
                if isinstance(item, WorkbookClient):
                    res = item.drive_item
                else:
                    res = dc.upload_file(item, **params)

                # Extract the necessary information and construct the attachment object
                attach_id = re.search('{(.*)}', res.get('eTag')).group(1)
                parent = res.get('parentReference')
                parent_folder = dc.get(f"/drives/{parent.get('driveId')}/items/{parent.get('id')}")

                body += f'<attachment id="{attach_id}"></attachment>'
                attach_list.append({
                    'id': attach_id,
                    'contentType': 'reference',
                    'contentUrl': parent_folder.get('webUrl') + '/' + res.get('name'),
                    'name': res.get('name')
                })

        # Compile the JSON
        json_body = {'body': {
            'contentType': 'html',
            'content': f'<div>{body}</div>'
        }}
        if mentions:
            json_body['mentions'] = mentions
        if hosted_content:
            json_body['hostedContents'] = hosted_content
        if attach_list:
            json_body['attachments'] = attach_list

        # Submit the POST request
        self.post(url, json=json_body)


    def get_chat_list(self, chat_name=None, example_member=None, one_on_one=False):
        """
            Helps you find the Chat ID of a chat, in case you want to send messages to a Chat.
            This method will only list Chats for which you are currently a member.

            Args:
                chat_name: String - If the Chat has been given a name, you can search for its name
                example_member: String - You can share the Display Name of somebody in the chat, to help
                    filter_strings down the results.  First or Last name also works.
                one_on_one: Boolean - True/False indicating whether the Chat is a one-on-one Chat or not.
        """
        # Reference: https://docs.microsoft.com/en-us/graph/query-parameters#filter-parameter
        filter_strings = []
        if chat_name:
            filter_strings.append(f"contains(topic, '{chat_name}')")
        if example_member:
            filter_strings.append(f"members/any(s:contains(s/displayName, '{example_member}'))")
        if one_on_one:
            filter_strings.append(f"chatType eq 'oneOnOne'")

        # Get the list of chats
        url = '/me/chats?$expand=members'
        if filter_strings:
            url += '&$filter=' + ' and '.join(filter_strings)
        res = self.get(url)

        return [
            {
                'id': chat.get('id'),
                'topic': chat.get('topic'),
                'chatType': chat.get('chatType'),
                'groupSize': len(chat.get('members')),
                'members': [
                    {
                        'name':  member.get('displayName'),
                        'email': member.get('email')
                    }
                    for member in chat.get('members')
                ]
            }
            for chat in res.get('value')
        ]
