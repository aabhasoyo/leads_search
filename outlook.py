from .core import CoreClient
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import base64
from pathlib import Path
import json
import requests

UPLOAD_LIMIT = 1024 * 1024 * 3  # 3 MB Simple Upload limit
DEFAULT_CHUNK_SIZE = 1024 * 1024 * 4  # 4 MB Default Chunk Size


class OutlookClient(CoreClient):
    """
        Constructs a custom HTTPClient to be used for requests against an Outlook Mailbox.

        This Client will act on behalf of an Azure User via an application registered through Azure AD.
    """

    def __init__(self, config, **kwargs):
        """
            Class constructor that accepts a User Email Address to the desired Outlook Mailbox.

            Args:
                config: An AuthConfig object configuring the Token Cache, or the username string.
        """

        # Super class sets up the resource path, so we collect credentials then run super init.
        super().__init__(config, scopes=['Mail.ReadWrite', 'Mail.Send'], **kwargs)

    def send_msg(self, msg):
        """
                    Send mime type email message. send_msg method supports attachments of size upto 3MB.
                    Args:
                        msg: mime type email message.
        """
        # encode the msg in base64 with inout from https://stackoverflow.com/questions/44902985/random-html-email-characters-replaced-with-in-outlookn "
        msg_base64 = base64.b64encode(bytes(msg.as_string().replace('\n', '\r\n'), 'utf-8'))
        self.post('/me/sendMail', headers={'Content-type': 'text/plain'}, data=msg_base64)

    def send_mail(self, subject, email_body, from_email, to_recipients, cc_recipients=None, bcc_recipients=None,
                  attachments=None,
                  email_body_type='text'):
        """
            Send an email with html or plain-text content type with attachments having less than 150MB size.
            Args:
                subject: subject of the email
                email_body: contents of the email in html or text string format
                from_email: sender's email address as a string
                to_recipients: list of email address strings the email is addressed to
                cc_recipients: list of cc email address strings with default value of None
                bcc_recipients: list of bcc email address strings with default value of None
                attachments: list of attachment file path strings, sum of the size of all email-attachments should be
                less than 150MB. Default is None.
                email_body_type: data type of email body which can be either html or plain-text type. Default is plain text.
        """

        # Create message container - the correct MIME type is multipart/alternative.
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email

        to_recipients = to_recipients if isinstance(to_recipients, list) else [to_recipients]
        msg['To'] = ', '.join(to_recipients)

        if cc_recipients is not None:
            cc_recipients = cc_recipients if isinstance(cc_recipients, list) else [cc_recipients]
            msg['CC'] = ', '.join(cc_recipients)

        if bcc_recipients is not None:
            bcc_recipients = bcc_recipients if isinstance(bcc_recipients, list) else [bcc_recipients]
            msg['BCC'] = ', '.join(bcc_recipients)

        # Record the MIME types of the body of the message (a plain-text or HTML version)
        part = MIMEText(email_body, email_body_type)
        # Attach the part into message container.
        msg.attach(part)

        # Add Attachments
        attachments_size = 0
        draft_attachments = []
        large_attachments = []

        if attachments is not None:
            attachments = attachments if isinstance(attachments, list) else [attachments]
            size_dict = dict([(attachments[i], Path(attachments[i]).stat().st_size) for i in range(0, len(attachments))])
            size_dict = dict(sorted(size_dict.items(), key=lambda item: item[1]))

            for i in size_dict.keys():
                if attachments_size + size_dict[i] < UPLOAD_LIMIT:
                    attachments_size += size_dict[i]
                    draft_attachments.append(i)
                else:
                    large_attachments.append(i)

            for i in range(0, len(draft_attachments)):
                attach_file = open(draft_attachments[i], 'rb')
                payload = MIMEBase('application', 'octet-stream')
                payload.set_payload(attach_file.read())
                encoders.encode_base64(payload)
                payload.add_header('Content-Disposition', 'attachment', filename=os.path.split(draft_attachments[i])[1])
                msg.attach(payload)
                attach_file.close()

        msg_base64 = base64.b64encode(bytes(msg.as_string().replace('\n', '\r\n'), 'utf-8'))

        if not large_attachments:
            self.post('/me/sendMail', headers={'Content-type': 'text/plain'}, data=msg_base64)

        else:
            # Create Draft message
            draft_msg = self.post('/me/messages', headers={'Content-type': 'text/plain'}, data=msg_base64)
            msg_id = draft_msg.get('id')

            for i in large_attachments:
                self.upload_attachment(msg_id, i)

            self.post('/me/messages/' + msg_id + '/send', headers={'Content-type': 'text/plain', 'Content-Length': '0'})

    def upload_attachment(self, msg_id, attachment, chunk_size=DEFAULT_CHUNK_SIZE):

        # Create an upload session
        file = Path(attachment)
        file_name = file.name
        file_size = file.stat().st_size

        data = json.dumps({"AttachmentItem": {"attachmentType": "file",
                                              "name": file_name,
                                              "size": file_size}})

        session_url = self.post('/me/messages/' + msg_id + '/attachments/createUploadSession',
                                headers={'Content-type': 'application/json'}, data=data).get('uploadUrl')

        current_bytes = 0
        with file.open(mode='rb') as f:
            while True:
                # Read a chunk, exit when data upload is done
                data = f.read(chunk_size)
                if not data:
                    break

                # Compile the header to track progress
                transfer_bytes = len(data)
                headers = {
                    'Content-Type': 'application/octet-stream',
                    'Content-Length': str(transfer_bytes),
                    'Content-Range': f'bytes {current_bytes}-{current_bytes + transfer_bytes - 1}/{file_size}'
                }
                current_bytes += transfer_bytes

                # Upload the chunk
                res = requests.put(session_url, data=data, headers=headers)

                # Check for errors, break if done
                res.raise_for_status()
                if res.status_code not in [200, 201, 202]:
                    return res.json()
