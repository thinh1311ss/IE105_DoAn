import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Phạm vi cần thiết
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service():
    """Khởi tạo và trả về dịch vụ Gmail API."""
    creds = None
    token_path = 'token.json'
    credentials_path = 'credentials.json'

    try:
        # Kiểm tra file token.json
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            logger.info("Đã tải token từ token.json")

        # Kiểm tra tính hợp lệ của credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Token đã hết hạn, đang làm mới...")
                try:
                    creds.refresh(Request())
                    logger.info("Đã làm mới token thành công")
                except Exception as e:
                    logger.error(f"Lỗi khi làm mới token: {str(e)}. Yêu cầu cấp quyền lại...")
                    creds = None  # Đặt creds thành None để yêu cầu cấp quyền mới
            else:
                logger.info("Không có token hợp lệ hoặc refresh token, yêu cầu xác thực mới...")

            # Nếu không có credentials hợp lệ, yêu cầu cấp quyền lại
            if not creds:
                if not os.path.exists(credentials_path):
                    logger.error(f"Không tìm thấy file credentials.json tại {credentials_path}")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                logger.info("Đã cấp quyền thành công, lưu token vào token.json")
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())

        # Khởi tạo dịch vụ Gmail
        service = build('gmail', 'v1', credentials=creds)
        logger.info("Dịch vụ Gmail API đã được khởi tạo thành công")
        return service

    except HttpError as e:
        logger.error(f"Lỗi HTTP khi khởi tạo dịch vụ Gmail: {str(e)} - Mã lỗi: {e.resp.status}")
        return None
    except Exception as e:
        logger.error(f"Lỗi không xác định khi khởi tạo dịch vụ Gmail: {str(e)}")
        return None