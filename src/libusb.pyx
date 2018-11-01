# cython
#
# Fast, Pythonic interface to libusb, and its asynchronous API.

from libc.stdint cimport *
from cpython.unicode cimport PyUnicode_Decode
from cpython.bytes cimport PyBytes_AsStringAndSize, PyBytes_FromStringAndSize
from cpython.bool cimport bool


cdef extern from "time.h" nogil:

    cdef struct timeval:
       long int tv_sec
       long int tv_usec

    cdef struct itimerval:
       timeval it_interval
       timeval it_value

cdef extern double floor(double)
cdef extern double fmod(double, double)

cdef extern from "libusb.h" nogil:

    struct _libusb_device_handle:
        pass
    ctypedef _libusb_device_handle libusb_device_handle

    struct _libusb_context:
        pass
    ctypedef _libusb_context libusb_context

    struct _libusb_device:
        pass
    ctypedef _libusb_device libusb_device


    # Descriptor types as defined by the USB specification.
    enum libusb_descriptor_type:
        # Device descriptor. See libusb_device_descriptor.
        LIBUSB_DT_DEVICE = 0x01

        # Configuration descriptor. See libusb_config_descriptor.
        LIBUSB_DT_CONFIG = 0x02

        # String descriptor
        LIBUSB_DT_STRING = 0x03

        # Interface descriptor. See libusb_interface_descriptor.
        LIBUSB_DT_INTERFACE = 0x04

        # Endpoint descriptor. See libusb_endpoint_descriptor.
        LIBUSB_DT_ENDPOINT = 0x05

        # BOS descriptor
        LIBUSB_DT_BOS = 0x0f

        # Device Capability descriptor
        LIBUSB_DT_DEVICE_CAPABILITY = 0x10

        # HID descriptor
        LIBUSB_DT_HID = 0x21

        # HID report descriptor
        LIBUSB_DT_REPORT = 0x22

        # Physical descriptor
        LIBUSB_DT_PHYSICAL = 0x23

        # Hub descriptor
        LIBUSB_DT_HUB = 0x29

        # SuperSpeed Hub descriptor
        LIBUSB_DT_SUPERSPEED_HUB = 0x2a

        # SuperSpeed Endpoint Companion descriptor
        LIBUSB_DT_SS_ENDPOINT_COMPANION = 0x30


    enum libusb_class_code:
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


    enum libusb_transfer_status:
        # Transfer completed without error. Note that this does not indicate
        # that the entire amount of requested data was transferred.
        LIBUSB_TRANSFER_COMPLETED

        # Transfer failed
        LIBUSB_TRANSFER_ERROR

        # Transfer timed out
        LIBUSB_TRANSFER_TIMED_OUT

        # Transfer was cancelled
        LIBUSB_TRANSFER_CANCELLED

        # For bulk/interrupt endpoints: halt condition detected (endpoint
        # stalled). For control endpoints: control request not supported.
        LIBUSB_TRANSFER_STALL

        # Device was disconnected
        LIBUSB_TRANSFER_NO_DEVICE

        # Device sent more data than requested
        LIBUSB_TRANSFER_OVERFLOW


    enum libusb_transfer_flags:
        # Report short frames as errors
        LIBUSB_TRANSFER_SHORT_NOT_OK = 1<<0

        # Automatically free() transfer buffer during libusb_free_transfer().
        # Note that buffers allocated with libusb_dev_mem_alloc() should not  be
        # attempted freed in this way, since free() is not an appropriate  way
        # to release such memory.
        LIBUSB_TRANSFER_FREE_BUFFER = 1<<1

        # Automatically call libusb_free_transfer() after callback returns.   If
        # this flag is set, it is illegal to call libusb_free_transfer()  from
        # your transfer callback, as this will result in a double-free  when
        # this flag is acted upon.
        LIBUSB_TRANSFER_FREE_TRANSFER = 1<<2

        # Terminate transfers that are a multiple of the endpoint's
        # wMaxPacketSize with an extra zero length packet. This is useful  when
        # a device protocol mandates that each logical request is  terminated by
        # an incomplete packet (i.e. the logical requests are  not separated by
        # other means).    This flag only affects host-to-device transfers to
        # bulk and interrupt  endpoints. In other situations, it is ignored.
        # This flag only affects transfers with a length that is a multiple of
        # the endpoint's wMaxPacketSize. On transfers of other lengths, this
        # flag has no effect. Therefore, if you are working with a device that
        # needs a ZLP whenever the end of the logical request falls on a packet
        # boundary, then it is sensible to set this flag on <em>every</em>
        # transfer (you do not have to worry about only setting it on transfers
        # that end on the boundary).    This flag is currently only supported on
        # Linux.   On other systems, libusb_submit_transfer() will return
        # LIBUSB_ERROR_NOT_SUPPORTED for every transfer where this flag is set.
        # Available since libusb-1.0.9.
        LIBUSB_TRANSFER_ADD_ZERO_PACKET = 1 << 3


    enum libusb_error:
        # Success (no error) #
        LIBUSB_SUCCESS = 0
        # Input#output error #
        LIBUSB_ERROR_IO = -1
        # Invalid parameter #
        LIBUSB_ERROR_INVALID_PARAM = -2
        # Access denied (insufficient permissions) /
        LIBUSB_ERROR_ACCESS = -3
        # No such device (it may have been disconnected) /
        LIBUSB_ERROR_NO_DEVICE = -4
        # Entity not found /
        LIBUSB_ERROR_NOT_FOUND = -5
        # Resource busy /
        LIBUSB_ERROR_BUSY = -6
        # Operation timed out /
        LIBUSB_ERROR_TIMEOUT = -7
        # Overflow /
        LIBUSB_ERROR_OVERFLOW = -8
        # Pipe error /
        LIBUSB_ERROR_PIPE = -9
        # System call interrupted (perhaps due to signal) /
        LIBUSB_ERROR_INTERRUPTED = -10
        # Insufficient memory /
        LIBUSB_ERROR_NO_MEM = -11
        # Operation not supported or unimplemented on this platform /
        LIBUSB_ERROR_NOT_SUPPORTED = -12
        # Other error /
        LIBUSB_ERROR_OTHER = -99


    enum libusb_endpoint_direction:
        # In: device-to-host
        LIBUSB_ENDPOINT_IN = 0x80,
        # Out: host-to-device
        LIBUSB_ENDPOINT_OUT = 0x00


    enum libusb_transfer_type:
        # Control endpoint /
        LIBUSB_TRANSFER_TYPE_CONTROL = 0

        # Isochronous endpoint
        LIBUSB_TRANSFER_TYPE_ISOCHRONOUS = 1

        # Bulk endpoint
        LIBUSB_TRANSFER_TYPE_BULK = 2

        # Interrupt endpoint
        LIBUSB_TRANSFER_TYPE_INTERRUPT = 3

        # Stream endpoint
        LIBUSB_TRANSFER_TYPE_BULK_STREAM = 4


    enum libusb_standard_request:
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


    enum libusb_request_type:
        LIBUSB_REQUEST_TYPE_STANDARD = (0x00 << 5)
        LIBUSB_REQUEST_TYPE_CLASS = (0x01 << 5)
        LIBUSB_REQUEST_TYPE_VENDOR = (0x02 << 5)
        LIBUSB_REQUEST_TYPE_RESERVED = (0x03 << 5)


    enum libusb_speed:
        # The OS doesn't report or know the device speed.
        LIBUSB_SPEED_UNKNOWN = 0
        # The device is operating at low speed (1.5MBit/s).
        LIBUSB_SPEED_LOW = 1
        # The device is operating at full speed (12MBit/s).
        LIBUSB_SPEED_FULL = 2
        # The device is operating at high speed (480MBit/s).
        LIBUSB_SPEED_HIGH = 3
        # The device is operating at super speed (5000MBit/s).
        LIBUSB_SPEED_SUPER = 4


    enum libusb_supported_speed:
        # Low speed operation supported (1.5MBit/s).
        LIBUSB_LOW_SPEED_OPERATION   = 1
        # Full speed operation supported (12MBit/s)
        LIBUSB_FULL_SPEED_OPERATION  = 2
        # High speed operation supported (480MBit/s)
        LIBUSB_HIGH_SPEED_OPERATION  = 4
        # Superspeed operation supported (5000MBit/s)
        LIBUSB_SUPER_SPEED_OPERATION = 8
        # Next will be SUPER_DUPER? ULTRA?

    enum libusb_request_recipient:
        LIBUSB_RECIPIENT_DEVICE = 0x00
        LIBUSB_RECIPIENT_INTERFACE = 0x01
        LIBUSB_RECIPIENT_ENDPOINT = 0x02
        LIBUSB_RECIPIENT_OTHER = 0x03


    struct libusb_control_setup:
        # Request type.
        # Bits 0:4 determine recipient, see libusb_request_recipient.
        # Bits 5:6 determine type, see libusb_request_type.
        # Bit 7 determines data transfer direction, see libusb_endpoint_direction.
        uint8_t  bmRequestType

        # Request. If the type bits of bmRequestType are equal to
        # libusb_request_type::LIBUSB_REQUEST_TYPE_STANDARD
        # "LIBUSB_REQUEST_TYPE_STANDARD" then this field refers to
        # libusb_standard_request. For other cases, use of this field is
        # application-specific.
        uint8_t  bRequest
        # Value. Varies according to request
        uint16_t wValue
        # Index. Varies according to request, typically used to pass an index or offset
        uint16_t wIndex
        # Number of bytes to transfer
        uint16_t wLength


    struct libusb_iso_packet_descriptor:
        unsigned int length
        unsigned int actual_length
        libusb_transfer_status status


    struct libusb_device_descriptor:
        # Size of this descriptor (in bytes)
        uint8_t  bLength

        # Descriptor type. Will have value libusb_descriptor_type::LIBUSB_DT_DEVICE
        # LIBUSB_DT_DEVICE in this context.
        uint8_t  bDescriptorType

        # USB specification release number in binary-coded decimal. A value of
        # 0x0200 indicates USB 2.0, 0x0110 indicates USB 1.1, etc.
        uint16_t bcdUSB

        # USB-IF class code for the device. See \ref libusb_class_code.
        uint8_t  bDeviceClass

        # USB-IF subclass code for the device, qualified by the bDeviceClass value
        uint8_t  bDeviceSubClass

        # USB-IF protocol code for the device, qualified by the bDeviceClass and
        # bDeviceSubClass values
        uint8_t  bDeviceProtocol

        # Maximum packet size for endpoint 0
        uint8_t  bMaxPacketSize0

        # USB-IF vendor ID
        uint16_t idVendor

        # USB-IF product ID
        uint16_t idProduct

        # Device release number in binary-coded decimal
        uint16_t bcdDevice

        # Index of string descriptor describing manufacturer
        uint8_t  iManufacturer

        # Index of string descriptor describing product
        uint8_t  iProduct

        # Index of string descriptor containing device serial number
        uint8_t  iSerialNumber

        # Number of possible configurations
        uint8_t  bNumConfigurations

    struct libusb_endpoint_descriptor:
        uint8_t  bLength
        uint8_t  bDescriptorType
        uint8_t  bEndpointAddress
        uint8_t  bmAttributes
        uint16_t wMaxPacketSize
        uint8_t  bInterval
        uint8_t  bRefresh
        uint8_t  bSynchAddress
        const unsigned char *extra
        int extra_length

    struct libusb_interface_descriptor:
        uint8_t  bLength
        uint8_t  bDescriptorType
        uint8_t  bInterfaceNumber
        uint8_t  bAlternateSetting
        uint8_t  bNumEndpoints
        uint8_t  bInterfaceClass
        uint8_t  bInterfaceSubClass
        uint8_t  bInterfaceProtocol
        uint8_t  iInterface
        libusb_endpoint_descriptor *endpoint
        unsigned char *extra
        int extra_length

    struct libusb_interface:
        libusb_interface_descriptor *altsetting
        int num_altsetting

    struct libusb_config_descriptor:
        uint8_t  bLength
        uint8_t  bDescriptorType
        uint16_t wTotalLength
        uint8_t  bNumInterfaces
        uint8_t  bConfigurationValue
        uint8_t  iConfiguration
        uint8_t  bmAttributes
        uint8_t  MaxPower
        libusb_interface *interface
        unsigned char *extra
        int extra_length

    struct libusb_transfer:
        pass

    ctypedef void (*libusb_transfer_cb_fn)(libusb_transfer *transfer)

    struct libusb_transfer:
        libusb_device_handle *dev_handle

        # A bitwise OR combination of libusb_transfer_flags.
        uint8_t flags

        # Address of the endpoint where this transfer will be sent.
        unsigned char endpoint

        # Type of the endpoint from libusb_transfer_type
        unsigned char type

        # Timeout for this transfer in millseconds. A value of 0 indicates no timeout.
        unsigned int timeout

        # The status of the transfer. Read-only, and only for use within transfer callback function.

        #  If this is an isochronous transfer, this field may read COMPLETED even
        #        if there were errors in the frames. Use the
        #        libusb_iso_packet_descriptor::status "status" field in each packet
        #        to determine if errors occurred.
        libusb_transfer_status status

        # Length of the data buffer
        int length

        # Actual length of data that was transferred. Read-only, and only for
        # use within transfer callback function. Not valid for isochronous
        # endpoint transfers.

        int actual_length

        # Callback function. This will be invoked when the transfer completes, fails, or is cancelled.
        libusb_transfer_cb_fn callback

        # User context data to pass to the callback function.
        void *user_data

        # Data buffer
        unsigned char *buffer

        # Number of isochronous packets. Only used for I/O with isochronous endpoints.
        int num_iso_packets

        # Isochronous packet descriptors, for isochronous transfers only.
        libusb_iso_packet_descriptor *iso_packet_desc

    ctypedef enum libusb_hotplug_flag:
        # Default value when not using any flags.
        LIBUSB_HOTPLUG_NO_FLAGS = 0
        # Arm the callback and fire it for all matching currently attached devices.
        LIBUSB_HOTPLUG_ENUMERATE = 1<<0

    ctypedef enum libusb_hotplug_event:
        # A device has been plugged in and is ready to use
        LIBUSB_HOTPLUG_EVENT_DEVICE_ARRIVED = 0x01

        # A device has left and is no longer available.  It is the user's
        # responsibility to call libusb_close on any handle associated with a
        # disconnected device.  It is safe to call libusb_get_device_descriptor
        # on a device that has left
        LIBUSB_HOTPLUG_EVENT_DEVICE_LEFT    = 0x02

    struct libusb_version:
        const uint16_t major;
        const uint16_t minor;
        const uint16_t micro;
        const uint16_t nano;
        const char *rc;
        const char* describe;

    int libusb_get_string_descriptor(libusb_device_handle *dev_handle,
                                     uint8_t desc_index,
                                     uint16_t langid,
                                     unsigned char *data, int length)

    void libusb_set_debug(libusb_context *ctx, int level)
    libusb_version *libusb_get_version()
    int libusb_has_capability(uint32_t capability)
    char * libusb_error_name(int errcode)
    int libusb_setlocale(const char *locale)
    const char * libusb_strerror(libusb_error errcode)

    int libusb_init(libusb_context **ctx)
    void libusb_exit(libusb_context *ctx)
    ssize_t libusb_get_device_list(libusb_context *ctx, libusb_device ***list)
    void libusb_free_device_list(libusb_device **list, int unref_devices)
    int libusb_open(libusb_device *dev, libusb_device_handle **dev_handle)
    void libusb_close(libusb_device_handle *dev_handle)
    int libusb_set_configuration(libusb_device_handle *dev_handle,
                                 int configuration)
    int libusb_claim_interface(libusb_device_handle *dev_handle,
                               int interface_number)
    int libusb_release_interface(libusb_device_handle *dev_handle,
                                 int interface_number)
    int libusb_get_configuration(libusb_device_handle *dev, int *config)
    int libusb_alloc_streams(libusb_device_handle *dev_handle, uint32_t num_streams,
                             unsigned char *endpoints, int num_endpoints)
    int libusb_free_streams(libusb_device_handle *dev_handle,
                            unsigned char *endpoints, int num_endpoints)
    libusb_device *libusb_get_device(libusb_device_handle *dev_handle)
    libusb_device *libusb_get_parent(libusb_device *dev)

    int libusb_set_interface_alt_setting(libusb_device_handle *dev_handle,
                                         int interface_number, int alternate_setting)
    int libusb_clear_halt(libusb_device_handle *dev_handle, unsigned char endpoint)
    int libusb_reset_device(libusb_device_handle *dev_handle)

    unsigned char * libusb_dev_mem_alloc(libusb_device_handle *dev_handle, size_t length)
    int libusb_dev_mem_free(libusb_device_handle *dev_handle, unsigned char *buffer, size_t length)

    int libusb_kernel_driver_active(libusb_device_handle *dev_handle, int interface_number)
    int libusb_detach_kernel_driver(libusb_device_handle *dev_handle, int interface_number)
    int libusb_attach_kernel_driver(libusb_device_handle *dev_handle, int interface_number)
    int libusb_set_auto_detach_kernel_driver( libusb_device_handle *dev_handle, int enable)

    int libusb_get_device_descriptor(libusb_device *dev, libusb_device_descriptor *desc)
    libusb_device *libusb_ref_device(libusb_device *dev)
    void libusb_unref_device(libusb_device *dev)
    int libusb_get_active_config_descriptor(libusb_device *dev,
            libusb_config_descriptor **config);
    int libusb_get_config_descriptor(libusb_device *dev,
            uint8_t config_index, libusb_config_descriptor **config)
    int libusb_get_config_descriptor_by_value(libusb_device *dev,
            uint8_t bConfigurationValue,
            libusb_config_descriptor **config)
    void libusb_free_config_descriptor(libusb_config_descriptor *config)

    libusb_transfer *libusb_alloc_transfer(int iso_packets)
    int libusb_submit_transfer(libusb_transfer *transfer)
    int libusb_cancel_transfer(libusb_transfer *transfer)
    void libusb_free_transfer(libusb_transfer *transfer)
    void libusb_transfer_set_stream_id(libusb_transfer *transfer,
                                       uint32_t stream_id)
    uint32_t libusb_transfer_get_stream_id(libusb_transfer *transfer)

    unsigned char *libusb_control_transfer_get_data(libusb_transfer *transfer)
    libusb_control_setup *libusb_control_transfer_get_setup(libusb_transfer *transfer)

    void libusb_fill_control_setup(
            unsigned char *buffer,
            uint8_t bmRequestType,
            uint8_t bRequest,
            uint16_t wValue,
            uint16_t wIndex,
            uint16_t wLength)

    void libusb_fill_control_transfer(
            libusb_transfer *transfer,
            libusb_device_handle *dev_handle,
            unsigned char *buffer,
            libusb_transfer_cb_fn callback,
            void *user_data,
            unsigned int timeout)

    void libusb_fill_bulk_transfer(
            libusb_transfer *transfer,
            libusb_device_handle *dev_handle,
            unsigned char endpoint,
            unsigned char *buffer,
            int length,
            libusb_transfer_cb_fn callback,
            void *user_data,
            unsigned int timeout)

    void libusb_fill_bulk_stream_transfer(
            libusb_transfer *transfer,
            libusb_device_handle *dev_handle,
            unsigned char endpoint,
            uint32_t stream_id,
            unsigned char *buffer,
            int length,
            libusb_transfer_cb_fn callback,
            void *user_data,
            unsigned int timeout)

    void libusb_fill_interrupt_transfer(
            libusb_transfer *transfer,
            libusb_device_handle *dev_handle,
            unsigned char endpoint,
            unsigned char *buffer,
            int length,
            libusb_transfer_cb_fn callback,
            void *user_data,
            unsigned int timeout)

    void libusb_fill_iso_transfer(
            libusb_transfer *transfer,
            libusb_device_handle *dev_handle,
            unsigned char endpoint,
            unsigned char *buffer,
            int length,
            int num_iso_packets,
            libusb_transfer_cb_fn callback,
            void *user_data,
            unsigned int timeout)

    void libusb_set_iso_packet_lengths(
            libusb_transfer *transfer,
            unsigned int length)

    unsigned char *libusb_get_iso_packet_buffer(
            libusb_transfer *transfer,
            unsigned int packet)

    unsigned char *libusb_get_iso_packet_buffer_simple(
            libusb_transfer *transfer,
            unsigned int packet)

    # sync I/O
    int libusb_control_transfer(libusb_device_handle *dev_handle,
                                uint8_t request_type,
                                uint8_t bRequest,
                                uint16_t wValue,
                                uint16_t wIndex,
                                unsigned char *data,
                                uint16_t wLength,
                                unsigned int timeout)

    int libusb_bulk_transfer(libusb_device_handle *dev_handle,
                             unsigned char endpoint,
                             unsigned char *data,
                             int length,
                             int *actual_length,
                             unsigned int timeout)

    int libusb_interrupt_transfer(libusb_device_handle *dev_handle,
                                  unsigned char endpoint,
                                  unsigned char *data,
                                  int length,
                                  int *actual_length,
                                  unsigned int timeout)

    int libusb_get_string_descriptor_ascii(libusb_device_handle *dev_handle,
                                           uint8_t desc_index,
                                           unsigned char *data,
                                           int length)

    int libusb_try_lock_events(libusb_context *ctx)
    void libusb_lock_events(libusb_context *ctx)
    void libusb_unlock_events(libusb_context *ctx)
    int libusb_event_handling_ok(libusb_context *ctx)
    int libusb_event_handler_active(libusb_context *ctx)
    void libusb_interrupt_event_handler(libusb_context *ctx)
    void libusb_lock_event_waiters(libusb_context *ctx)
    void libusb_unlock_event_waiters(libusb_context *ctx)
    int libusb_wait_for_event(libusb_context *ctx, timeval *tv)

    int libusb_handle_events_timeout(libusb_context *ctx, timeval *tv)
    int libusb_handle_events_timeout_completed(libusb_context *ctx,
                                               timeval *tv,
                                               int *completed)
    int libusb_handle_events(libusb_context *ctx)
    int libusb_handle_events_completed(libusb_context *ctx, int *completed)
    int libusb_handle_events_locked(libusb_context *ctx, timeval *tv)
    int libusb_pollfds_handle_timeouts(libusb_context *ctx)
    int libusb_get_next_timeout(libusb_context *ctx, timeval *tv)

    ctypedef int (*libusb_hotplug_callback_fn)(libusb_context *ctx,
                                               libusb_device *device,
                                               libusb_hotplug_event event,
                                               void *user_data)

    ctypedef int libusb_hotplug_callback_handle

    int libusb_hotplug_register_callback(libusb_context *ctx,
                                         libusb_hotplug_event events,
                                         libusb_hotplug_flag flags,
                                         int vendor_id,
                                         int product_id,
                                         int dev_class,
                                         libusb_hotplug_callback_fn cb_fn,
                                         void *user_data,
                                         libusb_hotplug_callback_handle *callback_handle)

# End cdef extern, Python objects follow.

# Descriptor sizes per descriptor type
DEF LIBUSB_DT_DEVICE_SIZE = 18
DEF LIBUSB_DT_CONFIG_SIZE = 9
DEF LIBUSB_DT_INTERFACE_SIZE = 9
DEF LIBUSB_DT_ENDPOINT_SIZE = 7
DEF LIBUSB_DT_ENDPOINT_AUDIO_SIZE = 9
DEF LIBUSB_DT_HUB_NONVAR_SIZE = 7
DEF LIBUSB_DT_SS_ENDPOINT_COMPANION_SIZE = 6
DEF LIBUSB_DT_BOS_SIZE = 5
DEF LIBUSB_DT_DEVICE_CAPABILITY_SIZE = 3


cpdef enum DeviceClass:
    PerInterface = LIBUSB_CLASS_PER_INTERFACE
    Audio = LIBUSB_CLASS_AUDIO
    Communication = LIBUSB_CLASS_COMM
    HID = LIBUSB_CLASS_HID
    Physical = LIBUSB_CLASS_PHYSICAL
    Printer = LIBUSB_CLASS_PRINTER
    Image = LIBUSB_CLASS_IMAGE
    MassStorage = LIBUSB_CLASS_MASS_STORAGE
    Hub = LIBUSB_CLASS_HUB
    Data = LIBUSB_CLASS_DATA
    SmartCard = LIBUSB_CLASS_SMART_CARD
    ContentSecurity = LIBUSB_CLASS_CONTENT_SECURITY
    Video = LIBUSB_CLASS_VIDEO
    PersonalHealthcare = LIBUSB_CLASS_PERSONAL_HEALTHCARE
    DiagnosticDevice = LIBUSB_CLASS_DIAGNOSTIC_DEVICE
    Wireless = LIBUSB_CLASS_WIRELESS
    Application = LIBUSB_CLASS_APPLICATION
    VendorSpecific = LIBUSB_CLASS_VENDOR_SPEC


cpdef enum RequestType:
    Standard = LIBUSB_REQUEST_TYPE_STANDARD
    Class = LIBUSB_REQUEST_TYPE_CLASS
    Vendor = LIBUSB_REQUEST_TYPE_VENDOR


cpdef enum RequestRecipient:
    Device = LIBUSB_RECIPIENT_DEVICE
    Interface = LIBUSB_RECIPIENT_INTERFACE
    Endpoint = LIBUSB_RECIPIENT_ENDPOINT
    Other = LIBUSB_RECIPIENT_OTHER


cpdef enum EndpointDirection:
    In = LIBUSB_ENDPOINT_IN  # In: device-to-host
    Out = LIBUSB_ENDPOINT_OUT  # Out: host-to-device


# If RequestType is Standard, this is the request.
cpdef enum StandardRequest:
    GetStatus = LIBUSB_REQUEST_GET_STATUS
    ClearFeature = LIBUSB_REQUEST_CLEAR_FEATURE
    SetFeature = LIBUSB_REQUEST_SET_FEATURE
    SetAddress = LIBUSB_REQUEST_SET_ADDRESS
    GetDescriptor = LIBUSB_REQUEST_GET_DESCRIPTOR
    SetDescriptor = LIBUSB_REQUEST_SET_DESCRIPTOR
    GetConfiguration = LIBUSB_REQUEST_GET_CONFIGURATION
    SetConfiguration = LIBUSB_REQUEST_SET_CONFIGURATION
    GetInterface = LIBUSB_REQUEST_GET_INTERFACE
    SetInterface = LIBUSB_REQUEST_SET_INTERFACE
    SynchFrame = LIBUSB_REQUEST_SYNCH_FRAME
    SetSel = LIBUSB_REQUEST_SET_SEL
    SetIsochronousDelay = LIBUSB_SET_ISOCH_DELAY


class UsbError(Exception):
    pass


class LibusbError(UsbError):

    def __init__(self, int err):
        self.errcode = err

    def __str__(self):
        cdef const char *errstr
        cdef libusb_error err
        err = self.errcode
        errstr = libusb_strerror(err)
        return errstr.decode("utf-8")


class UsbUsageError(UsbError):
    pass


cdef inline double _timeval2float(timeval *tv):
    return <double> tv.tv_sec + (<double> tv.tv_usec / 1000000.0)


cdef inline void _set_timeval(timeval *tv, double n):
    tv.tv_sec = <long> floor(n)
    tv.tv_usec = <long> (fmod(n, 1.0) * 1000000.0)


cdef uint16_t get_langid(libusb_device_handle *dev):
    cdef unsigned char buf[4]
    cdef int ret
    ret = libusb_get_string_descriptor(dev, 0, 0, buf, sizeof(buf))
    if (ret != sizeof(buf)):
        return 0
    return buf[2] | (buf[3] << 8)


cdef str get_string_descriptor(libusb_device_handle *handle, uint8_t descriptor,
                               unsigned char *buf, int buflen):
    cdef uint16_t langid
    cdef int r
    langid = get_langid(handle)
    if langid:
        r = libusb_get_string_descriptor(handle, descriptor, langid, buf, buflen)
        if r >= 2:
            return PyUnicode_Decode(<char *>buf + 2, r - 2, "UTF-16LE", "strict")
    return ""


cdef class UsbSession:
    """A USB Session.

    A unique session for accessing USB system. This is the only object you
    instantiate. All others are obtained from methods here, or other objects
    obtained from here.
    """
    cdef libusb_context* _ctx

    def __cinit__(self):
        libusb_init(&self._ctx)

    def __dealloc__(self):
        if self._ctx:
            libusb_exit(self._ctx)
            self._ctx = NULL

    @property
    def device_count(self):
        cdef ssize_t device_count
        cdef libusb_device **usb_devices
        device_count = libusb_get_device_list(self._ctx, &usb_devices)
        libusb_free_device_list(usb_devices, 1)
        return <int>device_count

    def find(self, int vid, int pid, str serial=None):
        cdef ssize_t device_count
        cdef libusb_device **usb_devices
        cdef libusb_device *device = NULL
        cdef libusb_device *check = NULL
        cdef libusb_device_descriptor desc
        cdef libusb_device_handle *handle
        cdef int r
        cdef unsigned char buf[256]

        device_count = libusb_get_device_list(self._ctx, &usb_devices)
        if device_count < 0:
            raise LibusbError(<int>device_count)
        if device_count > 0:
            for i in range(device_count):
                check = usb_devices[i]
                err = libusb_get_device_descriptor(check, &desc)
                if (desc.idProduct == pid and desc.idVendor == vid):
                    if serial and desc.iSerialNumber:
                        err = libusb_open(check, &handle)
                        if err:
                            raise LibusbError(<int>err)
                        langid = get_langid(handle)
                        if langid:
                            r = libusb_get_string_descriptor(handle,
                                       desc.iSerialNumber, langid, buf, 254)
                            if r >= 2:
                                s = PyUnicode_Decode(<char *>buf + 2, r - 2,
                                                        "UTF-16LE", "strict")
                                if serial == s:
                                    libusb_close(handle)
                                    device = check
                                    break
                                else:
                                    device = NULL
                        libusb_close(handle)
                    else:
                        device = check
                        break
        libusb_free_device_list(usb_devices, 1)
        if device:
            usbdev = UsbDevice(self)
            usbdev._device = device
            return usbdev
        else:
            return None


cdef class UsbDevice:
    cdef libusb_device* _device
    cdef libusb_device_handle* _handle
    # This is here just to keep the context alive if the session is deleted
    # before the devices.
    cdef UsbSession _session
    cdef str _serial

    def __cinit__(self, UsbSession _session):
        pass

    def __init__(self, UsbSession _session):
        self._session = _session
        self._serial = None

    def __del__(self):
        self._session = None

    def __dealloc__(self):
        if self._handle:
            libusb_close(self._handle)
        libusb_unref_device(self._device)

    def __str__(self):
        cdef libusb_device_descriptor desc
        cdef int r
        cdef uint16_t langid
        cdef unsigned char data[256]
        if self._handle:
            s = []
            err = libusb_get_device_descriptor(self._device, &desc)
            s.append("UsbDevice (open): VID:0x{:04x} PID:0x{:04x}".
                                          format(desc.idVendor, desc.idProduct))
            langid = get_langid(self._handle)
            if langid:
                if desc.iManufacturer:
                    s.append(get_string_descriptor(self._handle, desc.iManufacturer, data, 256))
                if desc.iProduct:
                    s.append(get_string_descriptor(self._handle, desc.iProduct, data, 256))
                if desc.iSerialNumber:
                    s.append(get_string_descriptor(self._handle, desc.iSerialNumber, data, 256))
            return " ".join(s)
        else:
            err = libusb_get_device_descriptor(self._device, &desc)
            return "UsbDevice (closed): VID:0x{:04x} PID:0x{:04x}".format(
                    desc.idVendor, desc.idProduct)

    def open(self):
        cdef libusb_device_handle *handle
        if self._handle:
            return
        err = libusb_open(self._device, &handle)
        if err:
            raise LibusbError(<int>err)
        self._handle = handle

    def close(self):
        if self._handle:
            libusb_close(self._handle)
            self._handle = NULL

    def reset(self):
        if self._handle:
            err = libusb_reset_device(self._handle)
            if err < 0:
                raise LibusbError(<int>err)
        else:
            raise UsbUsageError("Operation on closed device.")

    @property
    def parent(self):
        cdef libusb_device* parent
        cdef libusb_device **usb_devices
        libusb_get_device_list(self._session._ctx, &usb_devices)
        parent = libusb_get_parent(self._device)
        libusb_free_device_list(usb_devices, 1)
        if parent:
            usbdev = UsbDevice(self._session)
            usbdev._device = parent
            return usbdev
        else:
            return None

    @property
    def configuration(self):
        cdef int config
        if self._handle:
            err = libusb_get_configuration(self._handle, &config)
            if err:
                raise LibusbError(<int>err)
            else:
                return <int> config
        else:
            raise UsbUsageError("Operation on closed device.")

    @configuration.setter
    def configuration(self, int config):
        if self._handle:
            err = libusb_set_configuration(self._handle, <int> config)
            if err < 0:
                raise LibusbError(<int>err)
        else:
            raise UsbUsageError("Operation on closed device.")

    @property
    def serial(self):
        cdef libusb_device_descriptor desc
        cdef int r
        cdef uint16_t langid
        cdef unsigned char data[256]
        if self._serial is not None:
            return self._serial

        if self._handle:
            err = libusb_get_device_descriptor(self._device, &desc)
            langid = get_langid(self._handle)
            if langid:
                if desc.iSerialNumber:
                    r = libusb_get_string_descriptor(self._handle,
                                          desc.iSerialNumber, langid, data, 254)
                    if r >= 2:
                        s = PyUnicode_Decode(<char *>data + 2, r - 2,
                                                "UTF-16LE", "strict")
                        self._serial = s
                        return s
        raise UsbUsageError("Operation on closed device.")

    @property
    def VID(self):
        cdef libusb_device_descriptor desc
        libusb_get_device_descriptor(self._device, &desc)
        return <int> desc.idVendor

    @property
    def PID(self):
        cdef libusb_device_descriptor desc
        libusb_get_device_descriptor(self._device, &desc)
        return <int> desc.idProduct

    @property
    def Class(self):
        cdef libusb_device_descriptor desc
        libusb_get_device_descriptor(self._device, &desc)
        return DeviceClass(desc.bDeviceClass)

    @property
    def SubClass(self):
        cdef libusb_device_descriptor desc
        libusb_get_device_descriptor(self._device, &desc)
        return DeviceClass(desc.bDeviceSubClass)

    @property
    def num_configurations(self):
        cdef libusb_device_descriptor desc
        libusb_get_device_descriptor(self._device, &desc)
        return <int> desc.bNumConfigurations

    @property
    def configurations(self):
        cdef libusb_device_descriptor desc
        cdef libusb_config_descriptor *cfgdesc
        libusb_get_device_descriptor(self._device, &desc)
        for index in range(desc.bNumConfigurations):
            rv = libusb_get_config_descriptor(self._device, <uint8_t> index, &cfgdesc)
            if rv == 0:
                cfg = Configuration(self._session)
                cfg._descriptor = cfgdesc
                yield cfg

    @property
    def active_configuration(self):
        cdef libusb_config_descriptor *cfgdesc
        rv = libusb_get_active_config_descriptor(self._device, &cfgdesc)
        if rv == 0:
            cfg = Configuration(self._session)
            cfg._descriptor = cfgdesc
            return cfg
        else:
            raise LibusbError(<int>rv)

    def set_interface_alt_setting(self, int interface_number, int alternate_setting):
        if self._handle:
            err = libusb_set_interface_alt_setting(self._handle, <int> interface_number,
                                                   <int> alternate_setting)
            if err < 0:
                raise LibusbError(<int>err)
        else:
            raise UsbUsageError("Operation on closed device.")

    def detach_kernel_driver(self, int interface_number):
        if self._handle:
            err = libusb_detach_kernel_driver(self._handle, <int> interface_number)
            if err < 0:
                raise LibusbError(<int>err)
        else:
            raise UsbUsageError("Operation on closed device.")

    def attach_kernel_driver(self, int interface_number):
        if self._handle:
            err = libusb_attach_kernel_driver(self._handle, <int> interface_number)
            if err < 0:
                raise LibusbError(<int>err)
        else:
            raise UsbUsageError("Operation on closed device.")

    def is_kernel_driver_active(self, int interface_number):
        if self._handle:
            err = libusb_kernel_driver_active(self._handle, <int> interface_number)
            if err < 0:
                raise LibusbError(<int>err)
            if err == 0:
                return False
            if err == 1:
                return True
        else:
            raise UsbUsageError("Operation on closed device.")

    def set_auto_detach_kernel_driver(self, bool enable):
        if self._handle:
            err = libusb_set_auto_detach_kernel_driver(self._handle, <int> enable)
            if err < 0:
                raise LibusbError(<int>err)
        else:
            raise UsbUsageError("Operation on closed device.")

    def claim_interface(self, int interface_number):
        if self._handle:
            err = libusb_claim_interface(self._handle, <int> interface_number)
            if err < 0:
                raise LibusbError(<int>err)
        else:
            raise UsbUsageError("Operation on closed device.")

    def release_interface(self, int interface_number):
        if self._handle:
            err = libusb_release_interface(self._handle, <int> interface_number)
            if err < 0:
                raise LibusbError(<int>err)
        else:
            raise UsbUsageError("Operation on closed device.")

#    int libusb_alloc_streams(libusb_device_handle *dev_handle, uint32_t num_streams, unsigned char *endpoints, int num_endpoints)
#    int libusb_free_streams(libusb_device_handle *dev_handle, unsigned char *endpoints, int num_endpoints)

    def control_transfer(self,
                         RequestRecipient recipient,
                         RequestType type,
                         EndpointDirection direction,
                         int request,
                         int value,
                         int index,
                         bytes data):
        """General synchronous control transfer message.

        Args:
            recipient: A RequestRecipient indicating final destination.
            type: A RequestType indicating Standard, Class, or Vendor.
            direction: A EndpointDirection indicating In or Out transfer.
            request: int that is a StandardRequest value if type is
                     Standard, otherwise depends on application.
            value: int The message value parameter (?)
            index: int The message index parameter (?)
            data: bytes Sent to recipient if direction is Out

        Returns:
            bytes of response if direction is In

        Raises:
            UsbUsageError if called when device is not open.
        """
        cdef int xfer = 0
        cdef uint8_t request_type
        cdef char *bdata
        cdef Py_ssize_t bdata_length
        cdef bytes out

        if not self._handle:
            raise UsbUsageError("control_transfer on closed device.")
        # bmRequestType: the request type field for the setup packet
            # Bits 0:4 determine recipient, see libusb_request_recipient.
            # Bits 5:6 determine type, see libusb_request_type.
            # Bit 7 determines data transfer direction, see libusb_endpoint_direction.
        request_type = (direction & 0x80) | (type & 0x60) | (recipient & 0x1F)

        if (direction & 0x80):  # In: device-to-host
            out = PyBytes_FromStringAndSize(NULL, 65536)  # max size
            PyBytes_AsStringAndSize(out, &bdata, &bdata_length)
        else:  # host-to-device
            PyBytes_AsStringAndSize(data, &bdata, &bdata_length)
        xfer = libusb_control_transfer(self._handle,
                                       request_type,
                                       <uint8_t> request,
                                       <uint16_t> value,
                                       <uint16_t> index,
                                       <unsigned char *> bdata,
                                       <uint16_t> bdata_length,
                                       1000) # timeout (in millseconds)
        if xfer < 0:
            raise LibusbError(<int>xfer)
        if xfer > 0:
            if (direction & 0x80):  # In: device-to-host
                return out[:xfer]
        return b""


cdef class Configuration:
    cdef libusb_config_descriptor *_descriptor
    cdef UsbSession _session  # For the context
#        uint8_t  bLength
#        uint8_t  bDescriptorType
#        uint16_t wTotalLength
#        uint8_t  bNumInterfaces
#        uint8_t  bConfigurationValue
#        uint8_t  iConfiguration
#        uint8_t  bmAttributes
#        uint8_t  MaxPower
#        libusb_interface *interface
#        unsigned char *extra
#        int extra_length

    def __cinit__(self, UsbSession _session):
        self._descriptor = NULL

    def __init__(self, UsbSession _session):
        self._session = _session

    def __del__(self):
        self._session = None

    def __dealloc__(self):
        if self._descriptor:
            libusb_free_config_descriptor(self._descriptor)

    def __str__(self):
        return "Configuration: interfaces: {:d}".format(<int> self._descriptor.bNumInterfaces)

    @property
    def interfaces(self):
        pass

#cdef class Interface:
#    pass
#
#
#cdef class Endpoint:
#    pass


# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
