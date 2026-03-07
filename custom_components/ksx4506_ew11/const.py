DOMAIN = "ksx4506_ew11"
PLATFORMS = ["light", "switch", "climate", "fan", "sensor"]

CONF_HOST = "host"
CONF_PORT = "port"
CONF_TIMEOUT = "timeout"
CONF_RETRY = "retry"
CONF_CHECKSUM = "checksum"
CONF_STX = "stx"
CONF_ETX = "etx"
CONF_GAS_UNLOCK = "gas_unlock"

DEFAULT_PORT = 8899
DEFAULT_TIMEOUT = 3.0
DEFAULT_RETRY = 2
DEFAULT_CHECKSUM = "sum8"
DEFAULT_STX = "02"
DEFAULT_ETX = "03"

SIGNAL_DEVICE_UPDATE = f"{DOMAIN}_device_update"
SIGNAL_DEVICE_ADDED = f"{DOMAIN}_device_added"
