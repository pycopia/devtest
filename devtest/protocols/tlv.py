"""Provides a basis for implementing TLV style client-server protocols.

Messages types are defined in pure Python, and may be structured in any way.


- Message classes are encoded to byte strings.
- Network layer adapter for both sychronous and asynchronous applications.
- Message factories to simplify creating structured messages.
- Client base for implementing client side.
- Objects for implementing server side.
"""

from __future__ import annotations
# mypy: check-untyped-defs

from time import time
from abc import ABCMeta, abstractmethod
from io import BytesIO
from struct import Struct
from itertools import count
from pickle import Pickler, Unpickler
from socket import SocketType
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING

from devtest import ringbuffer

if TYPE_CHECKING:
    from devtest.typing import AnySocket, AsyncSocket
else:
    AnySocket = Any
    AsyncSocket = Any

# Protocol version.
VERSION = 1

_HEADER = Struct("!HH")


class Error(Exception):
    """An exception class that is also serializable as tlv message."""

    CODE: Optional[int] = None
    _ERROR_CODES: Dict[int, Any] = {}

    @classmethod
    def __init_subclass__(cls, *args, **kwargs):
        if cls.CODE is None:
            return
        assert cls.CODE is not None
        if cls.CODE in Error._ERROR_CODES:
            raise ProtocolDefinitionError(f"Duplicate exception code: {cls.CODE}")
        Error._ERROR_CODES[cls.CODE] = cls


class ProtocolError(Error):
    """Raised when protocol state becomes ambiguous."""
    CODE = 1


class ProtocolDefinitionError(Error):
    """Raised when a error is detected in the protocol definition."""
    CODE = 2


class ApplicationProtocolError(ProtocolError):
    CODE = 400


class ProtocolVersionError(ApplicationProtocolError):
    CODE = 401


class AuthenticationError(ApplicationProtocolError):
    CODE = 404


class UnhandledProtocolError(ApplicationProtocolError):
    CODE = 405


class ProtocolSequenceError(ApplicationProtocolError):
    CODE = 411


class ProtocolTypeError(ApplicationProtocolError):
    CODE = 412


class ApplicationError(Error):
    """Raised when some error happens in the user application."""
    CODE = 500


class ApplicationUsageError(Exception):
    """Raised when application client or server is not used correctly."""


def get_exception(code, message):
    """Find exception by code.

    Return:
        Exception instance with message.
    """
    excclass = Error._ERROR_CODES.get(code, Error)
    return excclass(message)


class Message(metaclass=ABCMeta):
    TAG: Optional[int] = None

    _MESSAGE_TAGS: Dict[int, Any] = {}

    def __init__(self, value: Any):
        self.value = value

    def __repr__(self):
        return f"{self.__class__.__name__}({self.value!r})"

    @classmethod
    def __init_subclass__(cls, *args, **kwargs):
        if cls.TAG is None:
            return
        assert cls.TAG is not None
        if cls.TAG in Message._MESSAGE_TAGS:
            raise ProtocolDefinitionError(f"Duplicate tag value: {cls.TAG}")
        Message._MESSAGE_TAGS[cls.TAG] = cls

    @classmethod
    def defined_messages(cls):
        return cls._MESSAGE_TAGS.items()

    @classmethod
    def new(cls, *args: Any, **kwargs: Any) -> Any:
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
    def new(cls, *args: Any) -> Any:
        return cls(str(args[0]))


class BytesMessage(Message):
    """Base class for messages with bytes payload.
    """

    def encode(self):
        return self.value

    @classmethod
    def decode(cls, data):
        return cls(data)

    @classmethod
    def new(cls, value) -> Any:
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
    def new(cls, value) -> Any:
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
    def new(cls, *args: Any) -> Any:
        return cls(float(args[0]))


class EmptyMessage(Message):
    """Base class for messages with no value content.
    """

    def encode(self):
        return b""

    @classmethod
    def decode(cls, data):
        return cls(None)

    @classmethod
    def new(cls) -> Any:
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


# Concrete messages follow.
# These are basic messages that all protocols may use.
# Tags 1-100 are reserved.


class Version(IntegerMessage):
    """Version of protocol.
    """
    TAG = 1

    @classmethod
    def new(cls, version=VERSION) -> Any:
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
    def new(cls, *others) -> Any:
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
    def new(cls) -> Any:
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
        elif isinstance(exception, type):
            if issubclass(exception, Error):
                exclass = exception
            else:
                raise ValueError("Need exception class or instance in response.")
        else:
            raise ValueError("Need exception class or instance in response.")
        return cls([ExceptionCode(exclass.CODE), ExceptionMessage.new(message)])

    def make_exception(self):
        """Make the right exception instance from this message."""
        code = self.value[0].value
        message = self.value[1].value
        return get_exception(code, message)


class ExceptionCode(IntegerMessage):
    TAG = 51


class ExceptionMessage(TextMessage):
    TAG = 52


# Some generally useful tags


class Command(Container):
    """Encode a shell command and arguments."""
    TAG = 110

    @classmethod
    def new(cls, argv):
        return cls([CommandArgument.new(o) for o in argv])


class CommandArgument(TextMessage):
    TAG = 111


class CommandResponse(Container):
    """Encode a shell command return value, standard output, and standard
    error.
    """
    TAG = 200

    @classmethod
    def new(cls, exitstatus, stdout, stderr):
        return cls([
            ExitStatus.new(exitstatus),
            StandardOutOutput.new(stdout),
            StandardErrorOutput.new(stderr)
        ])


class ExitStatus(IntegerMessage):
    TAG = 213


class StandardOutOutput(BytesMessage):
    TAG = 214


class StandardErrorOutput(BytesMessage):
    TAG = 215


# Higher level message construction


class _MessageFactory:
    """Base class for message factories.

    These construct and also validate tlv message.
    Provides base functions for constructing structured messages with sequence
    numbers.
    """

    _sequence_counter = count(1)

    def __init__(self):
        # message sequence number sent but not responded to.
        self._outstanding = set()

    def _request_message_base(self):
        """Return a new Container message with protocol prefix added."""
        seq = next(_MessageFactory._sequence_counter)
        self._outstanding.add(seq)
        return Container.new(Version(VERSION), Sequence(seq))

    def _response_message_base(self, message: List[Message]):
        """Return a new Container message with a response to a given received
        message.
        """
        seq = message[0].value
        myseq = next(_MessageFactory._sequence_counter)
        return Container.new(Version.new(VERSION), Sequence.new(myseq), Sequence.new(seq))

    def all_messages(self):
        """Get a list of all currently defined message types for this
        application.
        """
        return Message.defined_messages()

    def validate(self, msg) -> List:
        """Check the protocol version and that is has a minimum length.

        Returns:
            rest of message, version stripped.
        """
        msgversion, *rest = msg.value
        if msgversion.value != VERSION:
            raise ProtocolVersionError(f"Got version {msgversion.value}, expected {VERSION}.")
        if len(rest) <= 1:
            raise ApplicationProtocolError("No message body.")
        return rest

    def validate_response(self, msg: Message):
        """Validate response.

        Check sequence number is one of ours.
        If response encodes an exception (ErrorResponse), re-raise a
        reconstructed exception here.

        Returns:
            Message with version and sequence numbers stripped.
        """
        body = self.validate(msg)
        respseq, myseq, *body = body
        if myseq.value not in self._outstanding:
            raise ProtocolSequenceError(f"Got unexpected sequence number ({myseq}).")
        self._outstanding.remove(myseq.value)
        if isinstance(body[0], ErrorResponse):
            exc = body[0].make_exception()
            raise exc
        return body

    def validate_ok(self, msg):
        body = self.validate_response(msg)
        return isinstance(body[0], OKResponse)

    def is_goodbye(self, msg):
        plist = msg.value
        if len(plist) < 2:
            return False
        return isinstance(msg.value[2], Goodbye)


class ClientMessageFactory(_MessageFactory):
    """Message factory for process running as client.
    """

    def ping(self):
        return self._request_message_base().append(Ping.new())

    def hello(self):
        return self._request_message_base().append(HelloMessage.new())

    def goodbye(self):
        return self._request_message_base().append(Goodbye.new())

    def command(self, argv):
        return self._request_message_base().append(Command.new(argv))


class ServerMessageFactory(_MessageFactory):
    """Message factory for process running in server role.
    """

    def ok_response(self, clientmessage):
        return self._response_message_base(clientmessage).append(OKResponse.new())

    def hello_response(self, clientmessage):
        return self._response_message_base(clientmessage).append(HelloResponseMessage.new())

    def ping_response(self, clientmessage):
        return self._response_message_base(clientmessage).append(PingResponse.new())

    def error_response(self, clientmessage, exc, message="No message."):
        return self._response_message_base(clientmessage).append(ErrorResponse.new(exc, message))

    def command_response(self, clientmessage, exitstatus, stdout, stderr):
        return self._response_message_base(clientmessage).append(
            CommandResponse.new(exitstatus, stdout, stderr))


# Adapt to network with either synchronous or ashynchronous styles.


class _NetworkInterface:

    def __init__(self, sock: AnySocket):
        self._sock = sock

    def fileno(self):
        if self._sock is not None:
            return self._sock.fileno()
        else:
            return -1


class AsyncInterface(_NetworkInterface):
    """Asynchronous transaction interface.

    Requires a curio asynchronous socket.
    """

    def __init__(self, sock: AsyncSocket):
        self._sock: AsyncSocket = sock

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

    async def chat(self, msg: Message) -> Message:
        await self.send(msg)
        return await self.receive()


class SyncInterface(_NetworkInterface):
    """Blocking transaction interface.

    Requires a socket in blocking mode.
    """

    def __init__(self, sock: SocketType):
        self._sock = sock

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def send(self, msg: Message):
        value = msg.encode()
        ld = len(value)
        self._sock.send(_HEADER.pack(msg.TAG, ld))
        return self._sock.sendall(value)

    def receive(self) -> Message:
        s = self._sock
        s.settimeout(30.0)
        try:
            h = s.recv(_HEADER.size)
        finally:
            s.settimeout(None)
        if not h:
            raise EOFError()

        tag, length = _HEADER.unpack(h)
        data = s.recv(length)
        return _get_message(tag).decode(data)

    def chat(self, msg: Message) -> Message:
        self.send(msg)
        return self.receive()


class _ClosedInterface:
    """Stub interface in place of real interface when required."""

    def __getattr__(self, name):
        raise ApplicationProtocolError("No interface set.")

    def __bool__(self):
        return False


# Client and server bases
Interface = Union[SyncInterface, AsyncInterface, _ClosedInterface]


class ClientBase:
    """Base for client side of protocol.

    Provides public interface to protocol client user.
    """

    def __init__(self, factory=ClientMessageFactory):
        self._message_factory = factory()
        self._socketinterface: Interface = _ClosedInterface()

    def connect_socket(self, sock: SocketType):
        self._socketinterface = SyncInterface(sock)  # clients typically use sync code.

    def close(self):
        if self._socketinterface:
            self._socketinterface.close()
            self._socketinterface = _ClosedInterface()

    def hello(self) -> bool:
        """Validate connection by saying hello.

        Response should be "HELLO2U2" if everything is OK.

        Returns:
            True if proper response, False otherwise.
        """
        resp = self._socketinterface.chat(self._message_factory.hello())
        body = self._message_factory.validate_response(resp)
        return body[0].value == "HELLO2U2"

    def bye(self):
        """Tell the server that we are going to end this session. Then close.
        """
        self._socketinterface.send(self._message_factory.goodbye())
        self.close()

    def ping(self) -> float:
        """Check connection.

        Returns:
            time difference between this client and the server response time.
        """
        myping = self._message_factory.ping()
        resp = self._socketinterface.chat(myping)
        body = self._message_factory.validate_response(resp)
        return body[0].value - myping.value[2].value


# Server parts


class Handlers:
    """ Handlers class is a holder of coroutine methods that handle message
    requests for servers.


    Add methods named handle_X, for Message class named X (lowercased), to your subclass.
    """

    def __init__(self, factory):
        self._handlers = {}
        for tag, klass in factory.all_messages():
            method_name = f"handle_{klass.__name__.lower()}"
            handler_method = getattr(self, method_name, self.handle_default)
            self._handlers[tag] = handler_method
        self._factory = factory

    async def handle_default(self, message_body):
        msg = f"Unhandled message {message_body!r}"
        exc = UnhandledProtocolError(msg)
        return self._factory.error_response(message_body, exc, message=msg)

    async def dispatch(self, message_body):
        try:
            coro = self._handlers.get(message_body[1].TAG, self.handle_default)
            return await coro(message_body)
        except Exception as err:
            exc = ApplicationError(str(err))
            return self._factory.error_response(message_body, exc, message=str(err.args[0]))

    async def handle_hellomessage(self, message_body):
        return self._factory.hello_response(message_body)

    async def handle_ping(self, message_body):
        return self._factory.ping_response(message_body)


# In order to reduce dependencies of this module the server sample implementation is not here.

if __name__ == "__main__":
    # Example pickleable data
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
    print("\nSequence messages:")
    msg = Container.new(Sequence(2), TestPickleableMessage(DATA))
    print(msg)
    databytes = msg.encode()
    print(repr(databytes))
    newmsg = Container.decode(databytes)
    print(newmsg)
    print(newmsg.allvalues)

    print("\ntlv encode/decode:")
    # tlv encoder/decoder functions.
    rawmsg = encode_tlv(msg)
    rmsg = decode_tlv(rawmsg)
    print(rmsg.allvalues)

    print("\nError responses:")
    errresponse = ErrorResponse.new(ProtocolDefinitionError("PDE Instance"))
    print(errresponse)
    errresponse = ErrorResponse.new(ProtocolDefinitionError, "PDE class")
    print(errresponse)
    print(errresponse.encode())

    print("\nNested containers:")
    nestmsg = Container.new(Sequence(5), Container.new(Ping.new(), OKResponse.new()))
    print("nested msg:", nestmsg)
    nestbytes = encode_tlv(nestmsg)
    print("nested bytes:", nestbytes)
    print("nested decode:", decode_tlv(nestbytes))

    # message factory
    cmf = ClientMessageFactory()
    hm = cmf.hello()
    print(cmf.hello())
    print(cmf.validate(hm))
    print(cmf.ping())

    smf = ServerMessageFactory()
    print(smf.hello_response(smf.validate(hm)))

    exc = UnhandledProtocolError("Unhandled protocol tag test.")
    er = smf.error_response(smf.validate(hm), exc)
    print(er)

    cmdmsg = cmf.command(["ls"])
    print("Command message:", cmdmsg)
    print(encode_tlv(cmdmsg))
    resp = smf.command_response(smf.validate(cmdmsg), 0, b"out\n", b"errout\n")
    print(resp)
    print(encode_tlv(resp))
