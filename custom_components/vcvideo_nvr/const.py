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
RESULT_SUCCESS = "success"

# Error codes that mean "your session is gone, log in again" rather than
# "the request itself was bad". The NVR answers those with HTTP 200, so they
# have to be detected from the JSON body.
AUTH_ERROR_CODES = frozenset(
    {
        "csrf_token_error",
        "invalid_session",
        "invalid_token",
        "login_first",
        "no_login",
        "not_login",
        "session_invalid",
        "session_timeout",
        "user_not_login",
    }
)

# Channel connect status
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
STATUS_SLEEP = "sleep"
STATUS_NOT_CONFIGURED = "not_configured"

# Connect states in which a channel has no usable video at all.
STATUS_UNUSABLE = frozenset(
    {
        "not_configured",
        "notconfigured",
        "noconfig",
        "no_config",
    }
)
# Connect states in which the channel exists but is currently down.
STATUS_DOWN = frozenset(
    {
        "offline",
        "off_line",
        "disconnect",
        "disconnected",
    }
)

# Stream types
STREAM_TYPE_MAIN = 0
STREAM_TYPE_SUB = 1

# Update interval in seconds
UPDATE_INTERVAL = 30
HEARTBEAT_INTERVAL = 20

# Token header
HEADER_TOKEN = "X-csrftoken"

# --- Snapshot / thumbnail handling -------------------------------------------
# Most VCVideo NVR firmwares expose no HTTP still-image endpoint at all, so the
# thumbnail is grabbed from the RTSP stream with ffmpeg instead.
CONF_SNAPSHOT_SOURCE = "snapshot_source"
CONF_FFMPEG_ARGUMENTS = "ffmpeg_arguments"

SNAPSHOT_SOURCE_AUTO = "auto"
SNAPSHOT_SOURCE_HTTP = "http"
SNAPSHOT_SOURCE_RTSP_SUB = "rtsp_sub"
SNAPSHOT_SOURCE_RTSP_MAIN = "rtsp_main"
SNAPSHOT_SOURCE_NONE = "none"

SNAPSHOT_SOURCES = [
    SNAPSHOT_SOURCE_AUTO,
    SNAPSHOT_SOURCE_RTSP_SUB,
    SNAPSHOT_SOURCE_RTSP_MAIN,
    SNAPSHOT_SOURCE_HTTP,
    SNAPSHOT_SOURCE_NONE,
]

DEFAULT_SNAPSHOT_SOURCE = SNAPSHOT_SOURCE_AUTO
DEFAULT_FFMPEG_ARGUMENTS = "-rtsp_transport tcp"

# Home Assistant gives a camera 10 s to return a still image, so everything
# below has to finish well inside that budget.
SNAPSHOT_TIMEOUT = 8
SNAPSHOT_PROBE_TIMEOUT = 4
# Dashboards ask for the thumbnail of every camera at once; serving a cached
# frame keeps that from spawning one ffmpeg process per card per refresh.
SNAPSHOT_CACHE_SECONDS = 10
