# Copyright (C) 2020 by UsergeTeam@Github, < https://github.com/UsergeTeam >.
#
# This file is part of < https://github.com/UsergeTeam/Userge > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/uaudith/Userge/blob/master/LICENSE >
#
# All rights reserved.


import os
import io
import re
import time
import math
import pickle
import asyncio
from json import dumps
from threading import Thread
from datetime import datetime
from mimetypes import guess_type
from functools import wraps
from httplib2 import Http

from pySmartDL import SmartDL
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.client import HttpAccessTokenRefreshError, FlowExchangeError

from userge import userge, Message, Config, get_collection
from userge.utils import progress, humanbytes, time_formatter
from userge.utils.exceptions import ProcessCanceled

CREDS: object = None
AUTH_FLOW: object = None
PARENT_ID = ""

OAUTH_SCOPE = ["https://www.googleapis.com/auth/drive",
               "https://www.googleapis.com/auth/drive.file",
               "https://www.googleapis.com/auth/drive.metadata"]
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
G_DRIVE_DIR_MIME_TYPE = "application/vnd.google-apps.folder"
G_DRIVE_FILE_LINK = "📄 <a href='https://drive.google.com/open?id={}'>{}</a> __({})__"
G_DRIVE_FOLDER_LINK = "📁 <a href='https://drive.google.com/drive/folders/{}'>{}</a> __(folder)__"

LOG = userge.getLogger(__name__)
GDRIVE_COLLECTION = get_collection("gdrive")


class DBase:
    """
    Database Class for GDrive.
    """

    def __init__(self, id_: str) -> None:
        global CREDS

        self.__id = id_
        LOG.debug("Setting GDrive DBase...")

        if not CREDS:
            result = GDRIVE_COLLECTION.find_one({'_id': self.__id}, {'creds': 1})
            CREDS = pickle.loads(result['creds']) if result else None

        if CREDS:
            try:
                LOG.debug("Refreshing Creds...")
                CREDS.refresh(Http())

            except HttpAccessTokenRefreshError as h_e:
                LOG.exception(h_e)
                self._clear_creds()

    def _set_creds(self, creds) -> str:
        global CREDS

        LOG.info("Setting Creds...")
        CREDS = creds

        result = GDRIVE_COLLECTION.update_one(
            {'_id': self.__id}, {"$set": {'creds': pickle.dumps(creds)}}, upsert=True)

        if result.upserted_id:
            return "`Creds Added`"

        return "`Creds Updated`"

    def _clear_creds(self) -> str:
        global CREDS

        CREDS = None
        LOG.info("Creds Cleared!")

        if GDRIVE_COLLECTION.find_one_and_delete({'_id': self.__id}):
            return "`Creds Cleared`"

        return "`Creds Not Found`"


class GDrive(DBase):
    """
    GDrive Class For Search, Upload, Download, Copy, Move, Delete, EmptyTrash, ...
    """

    def __init__(self, id_: str) -> None:
        self._parent_id = PARENT_ID or Config.G_DRIVE_PARENT_ID
        self.__completed = 0
        self.__list = 1
        self.__progress = None
        self.__output = None
        self.__is_canceled = False
        self.__is_finished = False

        LOG.debug("Setting GDrive...")
        super().__init__(id_)

    def _cancel(self) -> None:
        self.__is_canceled = True

    def __finish(self) -> None:
        self.__is_finished = True

    @property
    def _is_canceled(self) -> bool:
        return self.__is_canceled

    @property
    def _is_finished(self) -> bool:
        return self.__is_finished

    @property
    def _progress(self) -> str:
        return self.__progress

    @property
    def _output(self) -> str:
        return self.__output

    @property
    def __service(self) -> object:
        return build("drive", "v3", credentials=CREDS, cache_discovery=False)

    @userge.new_thread
    def _search(self,
                search_query: str,
                flags: list,
                parent_id: str = "",
                list_root: bool = False) -> str:

        force = '-f' in flags
        pid = parent_id or self._parent_id

        if pid and not force:
            query = f"'{pid}' in parents and (name contains '{search_query}')"
        else:
            query = f"name contains '{search_query}'"

        page_token = None
        limit = int(flags.get('-l', 20))
        page_size = limit if limit < 50 else 50
        fields = 'nextPageToken, files(id, name, mimeType, size)'
        results = []
        msg = ""

        while True:
            response = self.__service.files().list(supportsTeamDrives=True,
                                                   includeTeamDriveItems=True,
                                                   q=query, spaces='drive',
                                                   corpora='allDrives', fields=fields,
                                                   pageSize=page_size,
                                                   orderBy='modifiedTime desc',
                                                   pageToken=page_token).execute()

            for file_ in response.get('files', []):

                if len(results) >= limit:
                    break

                if file_.get('mimeType') == G_DRIVE_DIR_MIME_TYPE:
                    msg += G_DRIVE_FOLDER_LINK.format(file_.get('id'), file_.get('name'))
                else:
                    msg += G_DRIVE_FILE_LINK.format(
                        file_.get('id'), file_.get('name'), humanbytes(int(file_.get('size', 0))))

                msg += '\n'
                results.append(file_)

            if len(results) >= limit:
                break

            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break

        del results

        if not msg:
            return "`Not Found!`"

        elif parent_id and not force:
            out = f"**List GDrive Folder** : `{parent_id}`\n"

        elif list_root and not force:
            out = f"**List GDrive Root Folder** : `{self._parent_id}`\n"

        else:
            out = f"**GDrive Search Query** : `{search_query}`\n"

        return out + f"**Limit** : `{limit}`\n\n__Results__ : \n\n" + msg

    def __set_permission(self, file_id: str) -> None:

        permissions = {'role': 'reader', 'type': 'anyone'}

        self.__service.permissions().create(fileId=file_id, body=permissions,
                                            supportsTeamDrives=True).execute()

        LOG.info("Set Permission : %s for Google-Drive File : %s", permissions, file_id)

    def __upload_file(self, file_path: str, parent_id: str) -> str:

        if self._is_canceled:
            raise ProcessCanceled

        mime_type = guess_type(file_path)[0] or "text/plain"
        file_name = os.path.basename(file_path)
        body = {"name": file_name, "mimeType": mime_type, "description": "Uploaded using Userge"}

        if parent_id:
            body["parents"] = [parent_id]

        if os.path.getsize(file_path) == 0:
            media_body = MediaFileUpload(file_path, mimetype=mime_type, resumable=False)

            u_file_obj = self.__service.files().create(body=body, media_body=media_body,
                                                       supportsTeamDrives=True).execute()
            file_id = u_file_obj.get("id")

        else:
            media_body = MediaFileUpload(file_path, mimetype=mime_type,
                                         chunksize=100*1024*1024, resumable=True)

            u_file_obj = self.__service.files().create(body=body, media_body=media_body,
                                                       supportsTeamDrives=True)

            c_time = time.time()
            response = None

            while response is None:
                status, response = u_file_obj.next_chunk()

                if self._is_canceled:
                    raise ProcessCanceled

                if status:
                    f_size = status.total_size
                    diff = time.time() - c_time
                    uploaded = status.resumable_progress
                    percentage = uploaded / f_size * 100
                    speed = round(uploaded / diff, 2)
                    eta = round((f_size - uploaded) / speed)

                    tmp = \
                        "__Uploading to GDrive...__\n" + \
                        "```[{}{}]({}%)```\n" + \
                        "**File Name** : `{}`\n" + \
                        "**File Size** : `{}`\n" + \
                        "**Uploaded** : `{}`\n" + \
                        "**Completed** : `{}/{}`\n" + \
                        "**Speed** : `{}/s`\n" + \
                        "**ETA** : `{}`"

                    self.__progress = tmp.format(
                        "".join(["█" for i in range(math.floor(percentage / 5))]),
                        "".join(["░" for i in range(20 - math.floor(percentage / 5))]),
                        round(percentage, 2),
                        file_name,
                        humanbytes(f_size),
                        humanbytes(uploaded),
                        self.__completed,
                        self.__list,
                        humanbytes(speed),
                        time_formatter(eta))

            file_id = response.get("id")

        if not Config.G_DRIVE_IS_TD:
            self.__set_permission(file_id)

        self.__completed += 1

        drive_file = self.__service.files().get(fileId=file_id, fields='id, name, size',
                                                supportsTeamDrives=True).execute()

        file_id = drive_file.get('id')
        file_name = drive_file.get("name")
        file_size = humanbytes(int(drive_file.get('size', 0)))

        LOG.info(
            "Created Google-Drive File => Name: %s ID: %s Size: %s", file_name, file_id, file_size)

        return G_DRIVE_FILE_LINK.format(file_id, file_name, file_size)

    def __create_drive_dir(self, dir_name: str, parent_id: str) -> str:

        if self._is_canceled:
            raise ProcessCanceled

        body = {"name": dir_name, "mimeType": G_DRIVE_DIR_MIME_TYPE}

        if parent_id:
            body["parents"] = [parent_id]

        file_ = self.__service.files().create(body=body, supportsTeamDrives=True).execute()

        file_id = file_.get("id")
        file_name = file_.get("name")

        if not Config.G_DRIVE_IS_TD:
            self.__set_permission(file_id)

        self.__completed += 1

        LOG.info("Created Google-Drive Folder => Name: %s ID: %s ", file_name, file_id)

        return file_id

    def __upload_dir(self, input_directory: str, parent_id: str) -> str:

        if self._is_canceled:
            raise ProcessCanceled

        list_dirs = os.listdir(input_directory)
        if len(list_dirs) == 0:
            return parent_id

        self.__list += len(list_dirs)

        new_id = None
        for item in list_dirs:
            current_file_name = os.path.join(input_directory, item)

            if os.path.isdir(current_file_name):
                current_dir_id = self.__create_drive_dir(item, parent_id)
                new_id = self.__upload_dir(current_file_name, current_dir_id)
            else:
                self.__upload_file(current_file_name, parent_id)
                new_id = parent_id

        return new_id

    def _upload(self, file_name: str) -> None:
        try:
            if os.path.isfile(file_name):
                self.__output = self.__upload_file(file_name, self._parent_id)
            else:
                folder_name = os.path.basename(os.path.abspath(file_name))
                dir_id = self.__create_drive_dir(folder_name, self._parent_id)
                self.__upload_dir(file_name, dir_id)
                self.__output = G_DRIVE_FOLDER_LINK.format(dir_id, folder_name)

        except HttpError as h_e:
            LOG.exception(h_e)
            self.__output = h_e

        except ProcessCanceled:
            self.__output = "`Process Canceled!`"

        finally:
            self.__finish()

    def __download_file(self, path: str, name: str, **kwargs) -> None:

        request = self.__service.files().get_media(fileId=kwargs['id'], supportsTeamDrives=True)

        with io.FileIO(os.path.join(path, name), 'wb') as d_f:
            d_file_obj = MediaIoBaseDownload(d_f, request, chunksize=100*1024*1024)

            c_time = time.time()
            done = False

            while done is False:
                status, done = d_file_obj.next_chunk()

                if self._is_canceled:
                    raise ProcessCanceled

                if status:
                    f_size = status.total_size
                    diff = time.time() - c_time
                    downloaded = status.resumable_progress
                    percentage = downloaded / f_size * 100
                    speed = round(downloaded / diff, 2)
                    eta = round((f_size - downloaded) / speed)

                    tmp = \
                        "__Downloading From GDrive...__\n" + \
                        "```[{}{}]({}%)```\n" + \
                        "**File Name** : `{}`\n" + \
                        "**File Size** : `{}`\n" + \
                        "**Downloaded** : `{}`\n" + \
                        "**Completed** : `{}/{}`\n" + \
                        "**Speed** : `{}/s`\n" + \
                        "**ETA** : `{}`"

                    self.__progress = tmp.format(
                        "".join(["█" for i in range(math.floor(percentage / 5))]),
                        "".join(["░" for i in range(20 - math.floor(percentage / 5))]),
                        round(percentage, 2),
                        name,
                        humanbytes(f_size),
                        humanbytes(downloaded),
                        self.__completed,
                        self.__list,
                        humanbytes(speed),
                        time_formatter(eta))

        self.__completed += 1
        LOG.info(
            "Downloaded Google-Drive File => Name: %s ID: %s", name, kwargs['id'])

    def __list_drive_dir(self, file_id: str) -> list:

        query = f"'{file_id}' in parents and (name contains '*')"
        fields = 'nextPageToken, files(id, name, mimeType)'
        page_token = None
        page_size = 100
        files = []

        while True:
            response = self.__service.files().list(supportsTeamDrives=True,
                                                   includeTeamDriveItems=True,
                                                   q=query, spaces='drive',
                                                   fields=fields, pageToken=page_token,
                                                   pageSize=page_size, corpora='allDrives',
                                                   orderBy='folder, name').execute()

            files.extend(response.get('files', []))
            page_token = response.get('nextPageToken', None)

            if page_token is None:
                break

            if self._is_canceled:
                raise ProcessCanceled

        return files

    def __create_server_dir(self, current_path: str, folder_name: str) -> str:
        path = os.path.join(current_path, folder_name)

        if not os.path.exists(path):
            os.mkdir(path)

        LOG.info("Created Folder => Name: %s", folder_name)
        self.__completed += 1

        return path

    def __download_dir(self, path: str, **kwargs) -> None:

        if self._is_canceled:
            raise ProcessCanceled

        files = self.__list_drive_dir(kwargs['id'])
        if len(files) == 0:
            return

        self.__list += len(files)

        for file_ in files:
            if file_['mimeType'] == G_DRIVE_DIR_MIME_TYPE:
                path_ = self.__create_server_dir(path, file_['name'])
                self.__download_dir(path_, **file_)
            else:
                self.__download_file(path, **file_)

    def _download(self, file_id: str) -> None:
        try:
            drive_file = self.__service.files().get(fileId=file_id, fields="id, name, mimeType",
                                                    supportsTeamDrives=True).execute()

            if drive_file['mimeType'] == G_DRIVE_DIR_MIME_TYPE:
                path = self.__create_server_dir(Config.DOWN_PATH, drive_file['name'])
                self.__download_dir(path, **drive_file)
            else:
                self.__download_file(Config.DOWN_PATH, **drive_file)

            self.__output = os.path.join(Config.DOWN_PATH, drive_file['name'])

        except HttpError as h_e:
            LOG.exception(h_e)
            self.__output = h_e

        except ProcessCanceled:
            self.__output = "`Process Canceled!`"

        finally:
            self.__finish()

    def __copy_file(self, file_id: str, parent_id: str) -> str:

        if self._is_canceled:
            raise ProcessCanceled

        body = {}
        if parent_id:
            body["parents"] = [parent_id]

        drive_file = self.__service.files().copy(
            body=body, fileId=file_id, supportsTeamDrives=True).execute()

        percentage = (self.__completed / self.__list) * 100

        tmp = \
            "__Copying Files In GDrive...__\n" + \
            "```[{}{}]({}%)```\n" + \
            "**Completed** : `{}/{}`"

        self.__progress = tmp.format(
            "".join(["█" for i in range(math.floor(percentage / 5))]),
            "".join(["░" for i in range(20 - math.floor(percentage / 5))]),
            round(percentage, 2),
            self.__completed,
            self.__list)

        self.__completed += 1

        LOG.info(
            "Copied Google-Drive File => Name: %s ID: %s", drive_file['name'], drive_file['id'])

        return drive_file['id']

    def __copy_dir(self, file_id: str, parent_id: str) -> str:

        if self._is_canceled:
            raise ProcessCanceled

        files = self.__list_drive_dir(file_id)
        if len(files) == 0:
            return parent_id

        self.__list += len(files)

        new_id = None
        for file_ in files:
            if file_['mimeType'] == G_DRIVE_DIR_MIME_TYPE:
                dir_id = self.__create_drive_dir(file_['name'], parent_id)
                new_id = self.__copy_dir(file_['id'], dir_id)
            else:
                self.__copy_file(file_['id'], parent_id)
                new_id = parent_id

        return new_id

    def _copy(self, file_id: str) -> None:
        try:
            drive_file = self.__service.files().get(
                fileId=file_id, fields="id, name, mimeType", supportsTeamDrives=True).execute()

            if drive_file['mimeType'] == G_DRIVE_DIR_MIME_TYPE:
                dir_id = self.__create_drive_dir(drive_file['name'], self._parent_id)
                self.__copy_dir(file_id, dir_id)
                ret_id = dir_id
            else:
                ret_id = self.__copy_file(file_id, self._parent_id)

            drive_file = self.__service.files().get(
                fileId=ret_id, fields="id, name, mimeType, size", supportsTeamDrives=True).execute()

            mime_type = drive_file['mimeType']
            file_name = drive_file['name']
            file_id = drive_file['id']

            if mime_type == G_DRIVE_DIR_MIME_TYPE:
                self.__output = G_DRIVE_FOLDER_LINK.format(file_id, file_name)
            else:
                file_size = humanbytes(int(drive_file.get('size', 0)))
                self.__output = G_DRIVE_FILE_LINK.format(file_id, file_name, file_size)

        except HttpError as h_e:
            LOG.exception(h_e)
            self.__output = h_e

        except ProcessCanceled:
            self.__output = "`Process Canceled!`"

        finally:
            self.__finish()

    @userge.new_thread
    def _move(self, file_id: str) -> str:

        previous_parents = ",".join(self.__service.files().get(
            fileId=file_id, fields='parents', supportsTeamDrives=True).execute()['parents'])

        drive_file = self.__service.files().update(fileId=file_id,
                                                   addParents=self._parent_id,
                                                   removeParents=previous_parents,
                                                   fields="id, name, mimeType, size, parents",
                                                   supportsTeamDrives=True).execute()

        LOG.info("Moved file : %s => "
                 "from : %s to : {drive_file['parents']} in Google-Drive",
                 file_id, previous_parents)

        mime_type = drive_file['mimeType']
        file_name = drive_file['name']
        file_id = drive_file['id']

        if mime_type == G_DRIVE_DIR_MIME_TYPE:
            return G_DRIVE_FOLDER_LINK.format(file_id, file_name)

        file_size = humanbytes(int(drive_file.get('size', 0)))
        return G_DRIVE_FILE_LINK.format(file_id, file_name, file_size)

    @userge.new_thread
    def _delete(self, file_id: str) -> None:

        self.__service.files().delete(fileId=file_id, supportsTeamDrives=True).execute()

        LOG.info("Deleted Google-Drive File : %s", file_id)

    @userge.new_thread
    def _empty_trash(self) -> None:

        self.__service.files().emptyTrash().execute()

        LOG.info("Empty Google-Drive Trash")

    @userge.new_thread
    def _get(self, file_id: str) -> str:

        drive_file = self.__service.files().get(fileId=file_id, fields='*',
                                                supportsTeamDrives=True).execute()

        drive_file['size'] = humanbytes(int(drive_file.get('size', 0)))
        drive_file['quotaBytesUsed'] = humanbytes(int(drive_file.get('quotaBytesUsed', 0)))

        drive_file = dumps(drive_file, sort_keys=True, indent=4)
        LOG.info("Getting Google-Drive File Details => %s", drive_file)

        return drive_file

    @userge.new_thread
    def _get_perms(self, file_id: str) -> str:

        perm_ids = self.__service.files().get(supportsTeamDrives=True, fileId=file_id,
                                              fields="permissionIds").execute()['permissionIds']
        all_perms = {}
        for perm_id in perm_ids:
            perm = self.__service.permissions().get(fileId=file_id, fields='*',
                                                    supportsTeamDrives=True,
                                                    permissionId=perm_id).execute()
            all_perms[perm_id] = perm

        all_perms = dumps(all_perms, sort_keys=True, indent=4)
        LOG.info("All Permissions: %s for Google-Drive File : %s", all_perms, file_id)

        return all_perms

    @userge.new_thread
    def _set_perms(self, file_id: str) -> str:

        self.__set_permission(file_id)

        drive_file = self.__service.files().get(fileId=file_id, supportsTeamDrives=True,
                                                fields="id, name, mimeType, size").execute()

        LOG.info(
            "Set Permission : for Google-Drive File : %s\n%s", file_id, drive_file)

        mime_type = drive_file['mimeType']
        file_name = drive_file['name']
        file_id = drive_file['id']

        if mime_type == G_DRIVE_DIR_MIME_TYPE:
            return G_DRIVE_FOLDER_LINK.format(file_id, file_name)

        file_size = humanbytes(int(drive_file.get('size', 0)))
        return G_DRIVE_FILE_LINK.format(file_id, file_name, file_size)

    @userge.new_thread
    def _del_perms(self, file_id: str) -> str:

        perm_ids = self.__service.files().get(fileId=file_id, supportsTeamDrives=True,
                                              fields="permissionIds").execute()['permissionIds']
        removed_perms = {}
        for perm_id in perm_ids:
            perm = self.__service.permissions().get(fileId=file_id, fields='*',
                                                    supportsTeamDrives=True,
                                                    permissionId=perm_id).execute()

            if perm['role'] != "owner":
                self.__service.permissions().delete(supportsTeamDrives=True, fileId=file_id,
                                                    permissionId=perm_id).execute()
                removed_perms[perm_id] = perm

        removed_perms = dumps(removed_perms, sort_keys=True, indent=4)
        LOG.info(
            "Remove Permission: %s for Google-Drive File : %s", removed_perms, file_id)

        return removed_perms


def creds_dec(func):
    """decorator for check CREDS"""

    @wraps(func)
    async def wrapper(self):
        if CREDS:
            await func(self)

        else:
            await self._Worker__message.edit("Please run `.gsetup` first", del_in=5)

    return wrapper


class Worker(GDrive):
    """
    Worker Class for GDrive.
    """

    def __init__(self, message: Message) -> None:
        self.__message = message
        super().__init__(message.from_user.id)

    def __get_file_id(self, filter_str: bool = False) -> tuple:
        link = self.__message.input_str

        if filter_str:
            link = self.__message.filtered_input_str

        found = re.search(r'https://drive.google.com/[\w\?\./&=]+([-\w]{33})', link)

        if found and 'folder' in link:
            out = (found.group(1), "folder")

        elif found:
            out = (found.group(1), "file")

        else:
            out = (link, "unknown")

        return out

    async def setup(self) -> None:
        """
        Setup GDrive.
        """
        global AUTH_FLOW

        if CREDS:
            await self.__message.edit("`Already Setup!`", del_in=5)
        else:
            AUTH_FLOW = OAuth2WebServerFlow(Config.G_DRIVE_CLIENT_ID,
                                            Config.G_DRIVE_CLIENT_SECRET,
                                            OAUTH_SCOPE,
                                            redirect_uri=REDIRECT_URI)

            reply_string = f"please visit {AUTH_FLOW.step1_get_authorize_url()} and "
            reply_string += "send back "
            reply_string += "<code>.gconf [auth_code]</code>"

            await self.__message.edit(
                text=reply_string, disable_web_page_preview=True)

    async def confirm_setup(self) -> None:
        """
        Finalize GDrive setup.
        """
        global AUTH_FLOW

        if AUTH_FLOW is None:
            await self.__message.edit("Please run `.gsetup` first", del_in=5)
            return

        await self.__message.edit("Checking Auth Code...")
        try:
            cred = AUTH_FLOW.step2_exchange(self.__message.input_str)

        except FlowExchangeError as c_i:
            LOG.exception(c_i)
            await self.__message.err(c_i)

        else:
            self._set_creds(cred)
            AUTH_FLOW = None

            await self.__message.edit("`Saved GDrive Creds!`", del_in=3, log=True)

    async def clear(self) -> None:
        """
        Clear Creds.
        """

        await self.__message.edit(self._clear_creds(), del_in=3, log=True)

    async def set_parent(self) -> None:
        """
        Set Parent id.
        """
        global PARENT_ID

        file_id, file_type = self.__get_file_id()

        if file_type != "folder":
            await self.__message.err("Please send me a folder link")

        else:
            PARENT_ID = file_id

            await self.__message.edit(
                f"Parents set as `{file_id}` successfully", del_in=5)

    async def reset_parent(self) -> None:
        """
        Reset parent id.
        """
        global PARENT_ID

        PARENT_ID = ""

        await self.__message.edit("`Parents Reset successfully`", del_in=5)

    @creds_dec
    async def search(self) -> None:
        """
        Search files in GDrive.
        """

        await self.__message.edit("`Loading GDrive Search...`")
        try:
            out = await self._search(
                self.__message.filtered_input_str, self.__message.flags)

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())
            return

        await self.__message.edit_or_send_as_file(
            out, disable_web_page_preview=True,
            caption=f"search results for `{self.__message.filtered_input_str}`")

    @creds_dec
    async def list_folder(self) -> None:
        """
        List files in GDrive folder or root.
        """

        file_id, file_type = self.__get_file_id(filter_str=True)

        if not file_id and not self._parent_id:
            await self.__message.edit("First set parent path by `.gset`", del_in=5)
            return

        if file_id and file_type != "folder":
            await self.__message.err("Please send me a folder link")
            return

        await self.__message.edit("`Loading GDrive List...`")

        root = not bool(file_id)

        try:
            out = await self._search('*', self.__message.flags, file_id, root)

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())
            return

        await self.__message.edit_or_send_as_file(
            out, disable_web_page_preview=True, caption=f"list results for `{file_id}`")

    @creds_dec
    async def upload(self) -> None:
        """
        Upload from file/folder/link/tg file to GDrive.
        """

        if not os.path.isdir(Config.DOWN_PATH):
            os.mkdir(Config.DOWN_PATH)

        replied = self.__message.reply_to_message
        is_url = re.search(
            r"(?:https?|ftp):\/\/[\w/\-?=%.]+\.[\w/\-?=%.]+", self.__message.input_str)
        dl_loc = None

        if replied and replied.media:
            await self.__message.edit("`Downloading From TG...`")
            c_time = time.time()

            dl_loc = await userge.download_media(
                message=replied,
                file_name=Config.DOWN_PATH,
                progress=progress,
                progress_args=(
                    "trying to download", userge, self.__message, c_time
                )
            )

            if self.__message.process_is_canceled:
                await self.__message.edit("`Process Canceled!`", del_in=5)
                return

            else:
                dl_loc = os.path.join(Config.DOWN_PATH, os.path.basename(dl_loc))

        elif is_url:
            await self.__message.edit("`Downloading From URL...`")

            is_url = is_url[0]
            file_name = os.path.basename(is_url)
            dl_loc = os.path.join(Config.DOWN_PATH, file_name)

            try:
                downloader = SmartDL(is_url, dl_loc, progress_bar=False)
                downloader.start(blocking=False)

                while not downloader.isFinished():
                    if self.__message.process_is_canceled:
                        downloader.stop()
                        raise Exception('Process Canceled!')

                    total_length = downloader.filesize if downloader.filesize else 0
                    downloaded = downloader.get_dl_size()
                    percentage = downloader.get_progress() * 100
                    speed = downloader.get_speed(human=True)
                    estimated_total_time = downloader.get_eta(human=True)

                    progress_str = \
                        "__{}__\n" + \
                        "```[{}{}]```\n" + \
                        "**Progress** : `{}%`\n" + \
                        "**URL** : `{}`\n" + \
                        "**FILENAME** : `{}`\n" + \
                        "**Completed** : `{}`\n" + \
                        "**Total** : `{}`\n" + \
                        "**Speed** : `{}`\n" + \
                        "**ETA** : `{}`"

                    progress_str = progress_str.format(
                        "trying to download",
                        ''.join(["█" for i in range(math.floor(percentage / 5))]),
                        ''.join(["░" for i in range(20 - math.floor(percentage / 5))]),
                        round(percentage, 2),
                        is_url,
                        file_name,
                        humanbytes(downloaded),
                        humanbytes(total_length),
                        speed,
                        estimated_total_time)

                    await self.__message.try_to_edit(
                        text=progress_str, disable_web_page_preview=True)

                    await asyncio.sleep(3)

            except Exception as d_e:
                await self.__message.err(d_e)
                return

        upload_file_name = dl_loc if dl_loc else self.__message.input_str

        if not os.path.exists(upload_file_name):
            await self.__message.err("invalid file path provided?")
            return

        await self.__message.edit("`Loading GDrive Upload...`")

        Thread(target=self._upload, args=(upload_file_name,)).start()
        start_t = datetime.now()

        while not self._is_finished:
            if self.__message.process_is_canceled:
                self._cancel()

            if self._progress is not None:
                await self.__message.try_to_edit(self._progress)

            await asyncio.sleep(3)

        if dl_loc and os.path.exists(dl_loc):
            os.remove(dl_loc)

        end_t = datetime.now()
        m_s = (end_t - start_t).seconds

        if isinstance(self._output, HttpError):
            out = f"**ERROR** : `{self._output._get_reason()}`"

        elif self._output is not None and not self._is_canceled:
            out = f"**Uploaded Successfully** __in {m_s} seconds__\n\n{self._output}"

        elif self._output is not None and self._is_canceled:
            out = self._output

        else:
            out = "`failed to upload.. check logs?`"

        await self.__message.edit(out, disable_web_page_preview=True, log=True)

    @creds_dec
    async def download(self) -> None:
        """
        Download file/folder from GDrive.
        """

        await self.__message.edit("`Loading GDrive Download...`")

        if not os.path.isdir(Config.DOWN_PATH):
            os.mkdir(Config.DOWN_PATH)

        file_id, _ = self.__get_file_id()

        Thread(target=self._download, args=(file_id,)).start()
        start_t = datetime.now()

        while not self._is_finished:
            if self.__message.process_is_canceled:
                self._cancel()

            if self._progress is not None:
                await self.__message.try_to_edit(self._progress)

            await asyncio.sleep(3)

        end_t = datetime.now()
        m_s = (end_t - start_t).seconds

        if isinstance(self._output, HttpError):
            out = f"**ERROR** : `{self._output._get_reason()}`"

        elif self._output is not None and not self._is_canceled:
            out = f"**Downloaded Successfully** __in {m_s} seconds__\n\n`{self._output}`"

        elif self._output is not None and self._is_canceled:
            out = self._output

        else:
            out = "`failed to download.. check logs?`"

        await self.__message.edit(out, disable_web_page_preview=True, log=True)

    @creds_dec
    async def copy(self) -> None:
        """
        Copy file/folder in GDrive.
        """

        if not self._parent_id:
            await self.__message.edit("First set parent path by `.gset`", del_in=5)
            return

        await self.__message.edit("`Loading GDrive Copy...`")

        file_id, _ = self.__get_file_id()

        Thread(target=self._copy, args=(file_id,)).start()
        start_t = datetime.now()

        while not self._is_finished:
            if self.__message.process_is_canceled:
                self._cancel()

            if self._progress is not None:
                await self.__message.try_to_edit(self._progress)

            await asyncio.sleep(3)

        end_t = datetime.now()
        m_s = (end_t - start_t).seconds

        if isinstance(self._output, HttpError):
            out = f"**ERROR** : `{self._output._get_reason()}`"

        elif self._output is not None and not self._is_canceled:
            out = f"**Copied Successfully** __in {m_s} seconds__\n\n{self._output}"

        elif self._output is not None and self._is_canceled:
            out = self._output

        else:
            out = "`failed to copy.. check logs?`"

        await self.__message.edit(out, disable_web_page_preview=True, log=True)

    @creds_dec
    async def move(self) -> None:
        """
        Move file/folder in GDrive.
        """

        if not self._parent_id:
            await self.__message.edit("First set parent path by `.gset`", del_in=5)
            return

        await self.__message.edit("`Loading GDrive Move...`")

        file_id, _ = self.__get_file_id()

        try:
            link = await self._move(file_id)

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())

        else:
            await self.__message.edit(
                f"`{file_id}` **Moved Successfully**\n\n{link}", log=True)

    @creds_dec
    async def delete(self) -> None:
        """
        Delete file/folder in GDrive.
        """

        await self.__message.edit("`Loading GDrive Delete...`")

        file_id, _ = self.__get_file_id()

        try:
            await self._delete(file_id)

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())

        else:
            await self.__message.edit(
                f"`{file_id}` **Deleted Successfully**", del_in=5, log=True)

    @creds_dec
    async def empty(self) -> None:
        """
        Empty GDrive Trash.
        """

        await self.__message.edit("`Loading GDrive Empty Trash...`")
        try:
            await self._empty_trash()

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())

        else:
            await self.__message.edit(
                "`Empty the Trash Successfully`", del_in=5, log=True)

    @creds_dec
    async def get(self) -> None:
        """
        Get details for file/folder in GDrive.
        """

        await self.__message.edit("`Loading GDrive GetDetails...`")

        file_id, _ = self.__get_file_id()

        try:
            meta_data = await self._get(file_id)

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())
            return

        out = f"**I Found these Details for** `{file_id}`\n\n{meta_data}"

        await self.__message.edit_or_send_as_file(
            out, disable_web_page_preview=True,
            caption=f"metadata for `{file_id}`")

    @creds_dec
    async def get_perms(self) -> None:
        """
        Get all Permissions of file/folder in GDrive.
        """

        await self.__message.edit("`Loading GDrive GetPermissions...`")

        file_id, _ = self.__get_file_id()

        try:
            out = await self._get_perms(file_id)

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())
            return

        out = f"**I Found these Permissions for** `{file_id}`\n\n{out}"

        await self.__message.edit_or_send_as_file(
            out, disable_web_page_preview=True,
            caption=f"view perm results for `{file_id}`")

    @creds_dec
    async def set_perms(self) -> None:
        """
        Set Permissions to file/folder in GDrive.
        """

        await self.__message.edit("`Loading GDrive SetPermissions...`")

        file_id, _ = self.__get_file_id()

        try:
            link = await self._set_perms(file_id)

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())

        else:
            out = f"**Set Permissions successfully for** `{file_id}`\n\n{link}"
            await self.__message.edit(out, disable_web_page_preview=True)

    @creds_dec
    async def del_perms(self) -> None:
        """
        Remove all permisiions of file/folder in GDrive.
        """

        await self.__message.edit("`Loading GDrive DelPermissions...`")

        file_id, _ = self.__get_file_id()

        try:
            out = await self._del_perms(file_id)

        except HttpError as h_e:
            LOG.exception(h_e)
            await self.__message.err(h_e._get_reason())
            return

        out = f"**Removed These Permissions successfully from** `{file_id}`\n\n{out}"

        await self.__message.edit_or_send_as_file(
            out, disable_web_page_preview=True,
            caption=f"removed perm results for `{file_id}`")


@userge.on_cmd("gsetup", about={'header': "Setup GDrive Creds"})
async def gsetup_(message: Message):
    """gsetup"""
    await Worker(message).setup()


@userge.on_cmd("gconf", about={
    'header': "Confirm GDrive Setup",
    'usage': ".gconf [auth token]"})
async def gconf_(message: Message):
    """gconf"""
    await Worker(message).confirm_setup()


@userge.on_cmd("gclear", about={'header': "Clear GDrive Creds"})
async def gclear_(message: Message):
    """gclear"""
    await Worker(message).clear()


@userge.on_cmd("gset", about={
    'header': "Set parent id",
    'description': "set destination by setting parent_id (root path). "
                   "this path is like working directory :)",
    'usage': ".gset [drive folder link]"})
async def gset_(message: Message):
    """gset"""
    await Worker(message).set_parent()


@userge.on_cmd("greset", about={'header': "Reset parent id"})
async def greset_(message: Message):
    """greset"""
    await Worker(message).reset_parent()


@userge.on_cmd("gfind", about={
    'header': "Search files in GDrive",
    'flags': {
        '-l': "add limit to search (default limit 20)",
        '-f': "add to do a force search"},
    'usage': ".gfind [search query]\n.gfind -l10 [search query]"})
async def gfind_(message: Message):
    """gfind"""
    await Worker(message).search()


@userge.on_cmd("gls", about={
    'header': "List files in GDrive Folder or Root",
    'flags': {'-l': "add limit to list (default limit 20)"},
    'usage': ".gls for view content in root\n.gls -l10 add limit to it\n"
             ".gls [drive folder link] (default limit 20)\n"
             ".gls -l10 [drive folder link] (add limit)"})
async def gls_(message: Message):
    """gls"""
    await Worker(message).list_folder()


@userge.on_cmd("gup", about={
    'header': "Upload files to GDrive",
    'description': "set destination by setting parent_id, "
                   "use `.gset` to set parent_id (root path).",
    'usage': ".gup [file / folder path | direct link | reply to telegram file]"})
async def gup_(message: Message):
    """gup"""
    await Worker(message).upload()


@userge.on_cmd("gdown", about={
    'header': "Download files from GDrive",
    'usage': ".gdown [file_id | file/folder link]"})
async def gdown_(message: Message):
    """gdown"""
    await Worker(message).download()


@userge.on_cmd("gcopy", about={
    'header': "Copy files in GDrive",
    'description': "set destination by setting parent_id, "
                   "use `.gset` to set parent_id (root path).",
    'usage': ".gcopy [file_id | file/folder link]"})
async def gcopy_(message: Message):
    """gcopy"""
    await Worker(message).copy()


@userge.on_cmd("gmove", about={
    'header': "Move files in GDrive",
    'description': "set destination by setting parent_id, "
                   "use `.gset` to set parent_id (root path).",
    'usage': ".gmove [file_id | file/folder link]"})
async def gmove_(message: Message):
    """gmove"""
    await Worker(message).move()


@userge.on_cmd("gdel", about={
    'header': "Delete files in GDrive",
    'usage': ".gdel [file_id | file/folder link]"})
async def gdel_(message: Message):
    """gdel"""
    await Worker(message).delete()


@userge.on_cmd("gempty", about={'header': "Empty the Trash"})
async def gempty_(message: Message):
    """gempty"""
    await Worker(message).empty()


@userge.on_cmd("gget", about={
    'header': "Get metadata from the given link in GDrive",
    'usage': ".gget [file_id | file/folder link]"})
async def gget_(message: Message):
    """gget"""
    await Worker(message).get()


@userge.on_cmd("ggetperm", about={
    'header': "Get permissions of file/folder in GDrive",
    'usage': ".ggetperm [file_id | file/folder link]"})
async def ggetperm_(message: Message):
    """ggetperm"""
    await Worker(message).get_perms()


@userge.on_cmd("gsetperm", about={
    'header': "Set permissions to file/folder in GDrive",
    'usage': ".gsetperm [file_id | file/folder link]"})
async def gsetperm_(message: Message):
    """gsetperm"""
    await Worker(message).set_perms()


@userge.on_cmd("gdelperm", about={
    'header': "Remove all permissions of file/folder in GDrive",
    'usage': ".gdelperm [file_id | file/folder link]"})
async def gdelperm_(message: Message):
    """gdelperm"""
    await Worker(message).del_perms()