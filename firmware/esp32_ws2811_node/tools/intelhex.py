# NOT HARDWARE VERIFIED.


class HexRecordError(Exception):
    pass


class IntelHex:
    def __init__(self, *args, **kwargs):
        raise HexRecordError(
            "Intel HEX parsing is unavailable in this compile-only PlatformIO environment"
        )
