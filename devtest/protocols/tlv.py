# python3.7
"""Implementation of TLV protocol base objects.
"""

from __future__ import annotations

from time import time
from abc import ABCMeta, abstractmethod
from io import BytesIO
from struct import Struct
from pickle import Pickler, Unpickler

from devtest import ringbuffer

# Protocol version.
VERSION = 1

_HEADER = Struct("!HH")


class Error(Exception):

    _ERROR_CODES = {}

    @classmethod
    def __init_subclass__(cls, *args, **kwargs):
        if cls.CODE is None:
            return
        if cls.CODE in Error._ERROR_CODES:
            raise ProtocolDefinitionError(f"Duplicate exception code: {cls.CODE}")
        Error._ERROR_CODES[cls.CODE] = cls


class ProtocolError(Error):
    CODE = 1


class ProtocolDefinitionError(Error):
    CODE = 2


def get_exception(code, message):
    """Find exception by code.

    Return:
        Exception instance with message.
    """
    excclass = Error._ERROR_CODES.get(code, Error)
    return excclass(message)


class Message(metaclass=ABCMeta):
    TAG = None

    _MESSAGE_TAGS = {}

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"{self.__class__.__name__}({self.value!r})"

    @classmethod
    def __init_subclass__(cls, *args, **kwargs):
        if cls.TAG is None:
            return
        if cls.TAG in Message._MESSAGE_TAGS:
            raise ProtocolDefinitionError(f"Duplicate tag value: {cls.TAG}")
        Message._MESSAGE_TAGS[cls.TAG] = cls

    @classmethod
    def defined_messages(cls):
        return cls._MESSAGE_TAGS.items()

    @classmethod
    def new(cls, *args, **kwargs):
        return cls(args[0])

    @abstractmethod
    def encode(self):
        """Encode current value attribute to byte string.
        """
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def decode(cls, data):
        """Decode a bytes string to Message object.
        """
        raise NotImplementedError()


def _get_message(tag):
    msgclass = Message._MESSAGE_TAGS.get(tag)
    if not msgclass:
        raise ProtocolError(f"Invalid tag: {tag}")
    return msgclass


class PickleableMessage(Message):
    """Base class for messages with any pickleable payload.

    Note: This message makes the message Python specific.
    """

    def encode(self):
        buf = ringbuffer.RingBuffer(2**16)
        pckler = Pickler(buf, protocol=-1, fix_imports=False)
        pckler.dump(self.value)
        if buf.freespace == 0:
            raise ProtocolError("Data too large.")
        return buf.read()

    @classmethod
    def decode(cls, data):
        buf = BytesIO(data)  # Unpickler needs a complete file-like object.
        unp = Unpickler(buf, fix_imports=False)
        return cls(unp.load())


class TextMessage(Message):
    """Base class for messages with text (unicode) payload.
    """

    def encode(self):
        return self.value.encode("utf8")

    @classmethod
    def decode(cls, data):
        return cls(data.decode("utf8"))

    @classmethod
    def new(cls, s):
        return cls(str(s))


class BytesMessage(Message):
    """Base class for messages with bytes payload.
    """

    def encode(self):
        return self.value

    @classmethod
    def decode(cls, data):
        return cls(data)

    @classmethod
    def new(cls, value):
        return cls(bytes(value))


class IntegerMessage(Message):
    """Base class for messages with signed integer value payload.
    """

    def encode(self):
        return self.value.to_bytes(4, byteorder="big", signed=True)

    @classmethod
    def decode(cls, data):
        return cls(int.from_bytes(data, byteorder="big", signed=True))

    @classmethod
    def new(cls, value):
        return cls(int(value))


class FloatMessage(Message):
    """Base class for messages with floating point value payload.
    """
    _PACKER = Struct("!d")

    def encode(self):
        return FloatMessage._PACKER.pack(self.value)

    @classmethod
    def decode(cls, data):
        return cls(FloatMessage._PACKER.unpack(data)[0])

    @classmethod
    def new(cls, val):
        return cls(float(val))


class EmptyMessage(Message):
    """Base class for messages with no value content.
    """

    def encode(self):
        return b""

    @classmethod
    def decode(cls, data):
        return cls(None)

    @classmethod
    def new(cls):
        return cls(None)


# Utility functions.


def decode_tlv(tlvdata):
    """decode TLV byte string to message object.
    """
    stream = BytesIO(tlvdata)
    h = stream.read(_HEADER.size)
    tag, length = _HEADER.unpack(h)
    data = stream.read(length)
    return _get_message(tag).decode(data)


def encode_tlv(msg):
    """Encode a message object to a TLV byte string.
    """
    data = msg.encode()
    h = _HEADER.pack(msg.TAG, len(data))
    return h + data


class AsyncInterface:
    """Asynchronous transaction interface."""

    def __init__(self, sock: socket):  # noqa
        self._sock = sock  # Asynchronous socket

    def fileno(self):
        if self._sock is not None:
            return self._sock.fileno()
        else:
            return -1

    async def close(self):
        if self._sock is not None:
            await self._sock.close()
            self._sock = None

    async def send(self, msg: Message):
        """Coroutine to send message object on stream.
        """
        sent = 0
        data = msg.encode()
        ld = len(data)
        await self._sock.send(_HEADER.pack(msg.TAG, ld))
        while sent < ld:
            sent += await self._sock.send(data)
        return sent

    async def receive(self) -> Message:
        """Coroutine to receive bytes on stream and decode to message object.
        """
        h = await self._sock.recv(_HEADER.size)
        if not h:
            raise EOFError()
        tag, length = _HEADER.unpack(h)
        data = await self._sock.recv(length)
        return _get_message(tag).decode(data)

    async def chat(self, msg):
        await self.send(msg)
        return await self.receive()


class SyncInterface:
    """Blocking transaction interface."""

    def __init__(self, sock: socket):  # noqa
        self._sock = sock  # Blocking socket

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def fileno(self):
        if self._sock is not None:
            return self._sock.fileno()
        else:
            return -1

    def send(self, msg: Message):
        value = msg.encode()
        ld = len(value)
        self._sock.send(_HEADER.pack(msg.TAG, ld))
        return self._sock.sendall(value)

    def receive(self) -> Message:
        s = self._sock
        h = s.recv(_HEADER.size)
        if not h:
            raise EOFError()
        tag, length = _HEADER.unpack(h)
        data = s.recv(length)
        return _get_message(tag).decode(data)

    def chat(self, msg):
        self.send(msg)
        return self.receive()


# Concrete messages follow.
# These are basic messages that all protocols may use.
# Tags 1-100 are reserved.


class Version(IntegerMessage):
    """Version of protocol.
    """
    TAG = 1

    @classmethod
    def new(cls, version=VERSION):
        return cls(version)


class Sequence(IntegerMessage):
    """Sequence number of command message.
    """
    TAG = 2


class Container(Message):
    """Sequence of other messages.

    The value attribute is a list.
    """
    TAG = 3

    @classmethod
    def new(cls, *others):
        messages = []
        for msg in others:
            if not isinstance(msg, Message):
                raise ValueError(f"Message list contains non-message: {msg}")
            messages.append(msg)
        return cls(messages)

    def encode(self):
        buf = ringbuffer.RingBuffer(2**16)
        for msg in self.value:
            msgdata = msg.encode()
            buf.write(_HEADER.pack(msg.TAG, len(msgdata)))
            buf.write(msgdata)
        if buf.freespace == 0:
            raise ProtocolError("Data too large for container.")
        return buf.read()

    @classmethod
    def decode(cls, data):
        messages = []
        stream = BytesIO(data)
        while True:
            h = stream.read(_HEADER.size)
            if not h:
                break
            tag, length = _HEADER.unpack(h)
            data = stream.read(length)
            msg = _get_message(tag).decode(data)
            messages.append(msg)
        return cls(messages)

    @property
    def values(self):
        return [m.value for m in self.value]

    @property
    def allvalues(self):
        return _get_all_values(self)

    def append(self, newmsg):
        self.value.append(newmsg)
        return self


def _get_all_values(container):
    rv = []
    for m in container.value:
        if isinstance(m, Container):
            rv.append(_get_all_values(m))
        else:
            rv.append(m.value)
    return rv


class Ping(FloatMessage):
    TAG = 4

    @classmethod
    def new(cls):
        return cls(time())


class PingResponse(FloatMessage):
    TAG = 5

    @classmethod
    def new(cls):
        return cls(time())


class HelloMessage(TextMessage):
    TAG = 6

    @classmethod
    def new(cls):
        return cls("HELLO")


class HelloResponseMessage(TextMessage):
    TAG = 7

    @classmethod
    def new(cls):
        return cls("HELLO2U2")


class Goodbye(EmptyMessage):
    TAG = 8


class OKResponse(EmptyMessage):
    TAG = 20


class ErrorResponse(Container):
    TAG = 50

    @classmethod
    def new(cls, exception, message="No message."):
        if isinstance(exception, Error):
            exclass = exception.__class__
            message = exception.args[0]
        elif issubclass(exception, Error):
            exclass = exception
        else:
            raise ValueError("Need exception class or instance in response.")
        return cls([ExceptionCode(exclass.CODE), ExceptionMessage.new(message)])

    def make_exception(self):
        code = self.value[0].value
        message = self.value[1].value
        return get_exception(code, message)


class ExceptionCode(IntegerMessage):
    TAG = 51


class ExceptionMessage(TextMessage):
    TAG = 52


if __name__ == "__main__":

    DATA = {1: "one", 2: "two"}

    msg = Ping.new()
    print(msg)
    print(Ping(time()))

    # Create concrete message subclass with unique tag.
    class TestPickleableMessage(PickleableMessage):
        TAG = 11

    msg = TestPickleableMessage(DATA)
    databytes = msg.encode()
    newdata = TestPickleableMessage.decode(databytes)
    assert newdata.value == DATA
    del msg

    # Sequence of messages
    print("Sequence messages:")
    msg = Container.new(Sequence(2), TestPickleableMessage(DATA))
    print(msg)
    databytes = msg.encode()
    print(repr(databytes))
    newmsg = Container.decode(databytes)
    print(newmsg)
    print(newmsg.allvalues)

    print("tlv encode/decode:")
    # tlv encoder/decoder functions.
    rawmsg = encode_tlv(msg)
    rmsg = decode_tlv(rawmsg)
    print(rmsg.allvalues)

    errresponse = ErrorResponse.new(ProtocolDefinitionError("PDE Instance"))
    print(errresponse)
    errresponse = ErrorResponse.new(ProtocolDefinitionError, "PDE class")
    print(errresponse)
    print(errresponse.encode())

    nestmsg = Container.new(Sequence(5), Container.new(Ping.new(), OKResponse.new()))
    print("nested msg:", nestmsg)
    nestbytes = encode_tlv(nestmsg)
    print("nested bytes:", nestbytes)
    print("nested decode:", decode_tlv(nestbytes))
