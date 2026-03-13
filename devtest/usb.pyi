# Fast, Pythonic interface to libusb, and its asynchronous API.

from typing import Iterator

LIBUSB_CLASS_PER_INTERFACE = 0
LIBUSB_CLASS_AUDIO = 1
LIBUSB_CLASS_COMM = 2
LIBUSB_CLASS_HID = 3
LIBUSB_CLASS_PHYSICAL = 5
LIBUSB_CLASS_PRINTER = 7
LIBUSB_CLASS_IMAGE = 6
LIBUSB_CLASS_MASS_STORAGE = 8
LIBUSB_CLASS_HUB = 9
LIBUSB_CLASS_DATA = 10
LIBUSB_CLASS_SMART_CARD = 0x0b
LIBUSB_CLASS_CONTENT_SECURITY = 0x0d
LIBUSB_CLASS_VIDEO = 0x0e
LIBUSB_CLASS_PERSONAL_HEALTHCARE = 0x0f
LIBUSB_CLASS_DIAGNOSTIC_DEVICE = 0xdc
LIBUSB_CLASS_WIRELESS = 0xe0
LIBUSB_CLASS_APPLICATION = 0xfe
LIBUSB_CLASS_VENDOR_SPEC = 0xff


class DeviceClass:
    PerInterface: int = LIBUSB_CLASS_PER_INTERFACE
    Audio: int = LIBUSB_CLASS_AUDIO
    Communication: int = LIBUSB_CLASS_COMM
    HID: int = LIBUSB_CLASS_HID
    Physical: int = LIBUSB_CLASS_PHYSICAL
    Printer: int = LIBUSB_CLASS_PRINTER
    Image: int = LIBUSB_CLASS_IMAGE
    MassStorage: int = LIBUSB_CLASS_MASS_STORAGE
    Hub: int = LIBUSB_CLASS_HUB
    Data: int = LIBUSB_CLASS_DATA
    SmartCard: int = LIBUSB_CLASS_SMART_CARD
    ContentSecurity: int = LIBUSB_CLASS_CONTENT_SECURITY
    Video: int = LIBUSB_CLASS_VIDEO
    PersonalHealthcare: int = LIBUSB_CLASS_PERSONAL_HEALTHCARE
    DiagnosticDevice: int = LIBUSB_CLASS_DIAGNOSTIC_DEVICE
    Wireless: int = LIBUSB_CLASS_WIRELESS
    Application: int = LIBUSB_CLASS_APPLICATION
    VendorSpecific: int = LIBUSB_CLASS_VENDOR_SPEC


LIBUSB_REQUEST_TYPE_STANDARD = (0x00 << 5)
LIBUSB_REQUEST_TYPE_CLASS = (0x01 << 5)
LIBUSB_REQUEST_TYPE_VENDOR = (0x02 << 5)


class RequestType:
    Standard: int = LIBUSB_REQUEST_TYPE_STANDARD
    Class: int = LIBUSB_REQUEST_TYPE_CLASS
    Vendor: int = LIBUSB_REQUEST_TYPE_VENDOR


LIBUSB_RECIPIENT_DEVICE = 0x00
LIBUSB_RECIPIENT_INTERFACE = 0x01
LIBUSB_RECIPIENT_ENDPOINT = 0x02
LIBUSB_RECIPIENT_OTHER = 0x03


class RequestRecipient:
    Device: int = LIBUSB_RECIPIENT_DEVICE
    Interface: int = LIBUSB_RECIPIENT_INTERFACE
    Endpoint: int = LIBUSB_RECIPIENT_ENDPOINT
    Other: int = LIBUSB_RECIPIENT_OTHER


LIBUSB_ENDPOINT_IN = 0x80
LIBUSB_ENDPOINT_OUT = 0x00


class EndpointDirection:
    In: int = LIBUSB_ENDPOINT_IN  # In: device-to-host
    Out: int = LIBUSB_ENDPOINT_OUT  # Out: host-to-device


LIBUSB_SPEED_UNKNOWN = 0
LIBUSB_SPEED_LOW = 1
LIBUSB_SPEED_FULL = 2
LIBUSB_SPEED_HIGH = 3
LIBUSB_SPEED_SUPER = 4


class Speed:
    Unknown: int = LIBUSB_SPEED_UNKNOWN  # The OS doesn't report or know the device speed.
    Low: int = LIBUSB_SPEED_LOW  # The device is operating at low speed (1.5MBit/s).
    Full: int = LIBUSB_SPEED_FULL  # The device is operating at full speed (12MBit/s).
    High: int = LIBUSB_SPEED_HIGH  # The device is operating at high speed (480MBit/s).
    Super: int = LIBUSB_SPEED_SUPER  # The device is operating at super speed (5000MBit/s).


LIBUSB_REQUEST_GET_STATUS = 0x00
LIBUSB_REQUEST_CLEAR_FEATURE = 0x01
LIBUSB_REQUEST_SET_FEATURE = 0x03
LIBUSB_REQUEST_SET_ADDRESS = 0x05
LIBUSB_REQUEST_GET_DESCRIPTOR = 0x06
LIBUSB_REQUEST_SET_DESCRIPTOR = 0x07
LIBUSB_REQUEST_GET_CONFIGURATION = 0x08
LIBUSB_REQUEST_SET_CONFIGURATION = 0x09
LIBUSB_REQUEST_GET_INTERFACE = 0x0A
LIBUSB_REQUEST_SET_INTERFACE = 0x0B
LIBUSB_REQUEST_SYNCH_FRAME = 0x0C
LIBUSB_REQUEST_SET_SEL = 0x30
LIBUSB_SET_ISOCH_DELAY = 0x31


class StandardRequest:
    GetStatus: int = LIBUSB_REQUEST_GET_STATUS
    ClearFeature: int = LIBUSB_REQUEST_CLEAR_FEATURE
    SetFeature: int = LIBUSB_REQUEST_SET_FEATURE
    SetAddress: int = LIBUSB_REQUEST_SET_ADDRESS
    GetDescriptor: int = LIBUSB_REQUEST_GET_DESCRIPTOR
    SetDescriptor: int = LIBUSB_REQUEST_SET_DESCRIPTOR
    GetConfiguration: int = LIBUSB_REQUEST_GET_CONFIGURATION
    SetConfiguration: int = LIBUSB_REQUEST_SET_CONFIGURATION
    GetInterface: int = LIBUSB_REQUEST_GET_INTERFACE
    SetInterface: int = LIBUSB_REQUEST_SET_INTERFACE
    SynchFrame: int = LIBUSB_REQUEST_SYNCH_FRAME
    SetSel: int = LIBUSB_REQUEST_SET_SEL
    SetIsochronousDelay: int = LIBUSB_SET_ISOCH_DELAY


LIBUSB_TRANSFER_TYPE_CONTROL = 0
LIBUSB_TRANSFER_TYPE_ISOCHRONOUS = 1
LIBUSB_TRANSFER_TYPE_BULK = 2
LIBUSB_TRANSFER_TYPE_INTERRUPT = 3
LIBUSB_TRANSFER_TYPE_BULK_STREAM = 4


class TransferType:
    Control: int = LIBUSB_TRANSFER_TYPE_CONTROL
    Isochronous: int = LIBUSB_TRANSFER_TYPE_ISOCHRONOUS
    Bulk: int = LIBUSB_TRANSFER_TYPE_BULK
    Interrupt: int = LIBUSB_TRANSFER_TYPE_INTERRUPT
    BulkStream: int = LIBUSB_TRANSFER_TYPE_BULK_STREAM


class UsbError(Exception):
    pass


class LibusbError(UsbError):

    def __init__(self, err: int):
        ...


class UsbUsageError(UsbError):

    def __init__(self, message: str):
        ...


class UsbEndpoint:

    @property
    def transfer_type(self) -> TransferType:
        ...

    @property
    def direction(self) -> EndpointDirection:
        ...

    @property
    def address(self) -> int:
        ...

    @property
    def max_packet_size(self) -> int:
        ...

    @property
    def extra(self) -> bytes:
        ...


class UsbInterface:

    @property
    def endpoints(self) -> Iterator[UsbEndpoint]:
        ...

    @property
    def Class(self) -> DeviceClass:
        ...

    @property
    def subclass(self) -> int:
        ...

    @property
    def protocol(self) -> int:
        ...


class Configuration:

    @property
    def interfaces(self) -> Iterator[UsbInterface]:
        ...


class UsbDevice:

    def open(self):
        ...

    def close(self):
        ...

    def reset(self):
        ...

    def clear_halt(self, endpoint: int):
        pass

    @property
    def parent(self) -> "UsbDevice" | None:
        ...

    @property
    def configuration(self) -> int:
        ...

    @configuration.setter
    def configuration(self, config: int):
        ...

    @property
    def serial(self) -> str | None:
        ...

    @property
    def VID(self) -> int:
        ...

    @property
    def PID(self) -> int:
        ...

    @property
    def bus_number(self) -> int:
        ...

    @property
    def port_number(self) -> int:
        ...

    @property
    def speed(self) -> Speed:
        ...

    @property
    def Class(self) -> DeviceClass:
        ...

    @property
    def subclass(self) -> DeviceClass:
        ...

    @property
    def num_configurations(self) -> int:
        ...

    @property
    def configurations(self) -> Iterator[Configuration]:
        ...

    @property
    def active_configuration(self) -> Configuration:
        ...

    def set_interface_alt_setting(self, interface_number: int, alternate_setting: int):
        ...

    def detach_kernel_driver(self, interface_number: int):
        ...

    def attach_kernel_driver(self, interface_number: int):
        ...

    def is_kernel_driver_active(self, interface_number: int) -> bool:
        ...

    def set_auto_detach_kernel_driver(self, enable: bool):
        ...

    def claim_interface(self, interface_number: int):
        ...

    def release_interface(self, interface_number: int):
        ...

    def control_transfer(self,
                         recipient: RequestRecipient,
                         rtype: RequestType,
                         direction: EndpointDirection,
                         request: int,
                         value: int,
                         index: int,
                         data_or_length: bytes | int) -> bytes | int:
        ...

    def bulk_transfer(self,
                      endpoint: int,
                      direction: EndpointDirection,
                      data_or_length: bytes | int,
                      timeout: int = 5000):
        ...

    def interrupt_transfer(self,
                           endpoint: int,
                           direction: EndpointDirection,
                           data_or_length: bytes | int,
                           timeout: int = 5000):
        ...


class UsbSession:
    """A USB Session.

    A unique session for accessing USB system. This is the only object you
    instantiate. All others are obtained from methods here, or other objects
    obtained from here.
    """
    @property
    def version(self) -> str:
        ...

    @property
    def device_count(self) -> int:
        ...

    @property
    def has_hotplug(self) -> bool:
        ...

    @property
    def has_hid_access(self) -> bool:
        ...

    @property
    def supports_detach_kernel_driver(self) -> bool:
        ...

    def find(self, vid: int, pid: int, serial: str | None = None) -> UsbDevice | None:
        ...

    def findall(self, vid: int, pid: int) -> list[UsbDevice]:
        ...
