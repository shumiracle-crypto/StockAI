import json
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    service_account_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    info = json.loads(service_account_json)

    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=SCOPES,
    )

    return build("drive", "v3", credentials=credentials)


def upload_or_update_file(file_path: Path, folder_id: str):
    service = get_drive_service()
    filename = file_path.name

    query = (
        f"name='{filename}' "
        f"and '{folder_id}' in parents "
        f"and trashed=false"
    )

    result = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
    ).execute()

    files = result.get("files", [])

    media = MediaFileUpload(
        str(file_path),
        mimetype="text/csv",
        resumable=False,
    )

    if files:
        file_id = files[0]["id"]
        service.files().update(
            fileId=file_id,
            media_body=media,
        ).execute()
        print(f"更新完了: {filename}")
    else:
        metadata = {
            "name": filename,
            "parents": [folder_id],
        }
        service.files().create(
            body=metadata,
            media_body=media,
            fields="id",
        ).execute()
        print(f"新規作成完了: {filename}")