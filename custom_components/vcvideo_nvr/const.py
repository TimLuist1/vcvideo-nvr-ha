"""Constants for the VCVideo NVR integration."""

DOMAIN = "vcvideo_nvr"
MANUFACTURER = "VCVideo"
DEFAULT_PORT = 80
DEFAULT_RTSP_PORT = 554
CONF_RTSP_PORT = "rtsp_port"

# API endpoints
API_BASE = "/API"
API_LOGIN = "/API/Web/Login"
API_LOGOUT = "/API/Web/Logout"
API_LOGIN_RANGE = "/API/Login/Range"
API_CHANNEL_INFO = "/API/Login/ChannelInfo/Get"
API_DEVICE_INFO = "/API/Login/DeviceInfo/Get"
API_STREAM_URL = "/API/Preview/StreamUrl"
API_HEARTBEAT = "/API/Login/Heartbeat"
API_SYSTEM_BASE = "/API/SystemInfo/Base"

# Request/response fields
FIELD_VERSION = "version"
FIELD_DATA = "data"
FIELD_RESULT = "result"
FIELD_REASON = "reason"
FIELD_ERROR_CODE = "error_code"
FIELD_TOKEN = "token"

API_VERSION = "1.0"

# Channel connect status
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
STATUS_SLEEP = "sleep"
STATUS_NOT_CONFIGURED = "not_configured"

# Stream types
STREAM_TYPE_MAIN = 0
STREAM_TYPE_SUB = 1

# Update interval in seconds
UPDATE_INTERVAL = 30
HEARTBEAT_INTERVAL = 20

# Token header
HEADER_TOKEN = "X-csrftoken"
