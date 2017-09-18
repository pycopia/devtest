"""
Implementation of JSON codec for general test framework.
"""

import json


class JSONSettingsError(TypeError):
    pass


class Encoder(json.JSONEncoder):
    """Encodes Python objects into JSON, and provides means to encode other
    Python objects.
    """
    def __init__(self):
        super(Encoder, self).__init__(ensure_ascii=False)


class Decoder(json.JSONDecoder):
    """Decodes JSON into Python objects, and reconstitutes additional Python
    objects that were encoded by the encoder in this module.
    """
    def __init__(self):
        super(Decoder, self).__init__()


_decoder = Decoder()
_encoder = Encoder()


def decode_bytes(data):
    """Decode JSON serialized byte string, with possible embedded Python objects.
    """
    return _decoder.decode(data.decode("utf-8"))


def decode(data):
    """Decode JSON serialized string, with possible embedded Python objects.
    """
    return _decoder.decode(data)


def encode_bytes(data):
    """Encode Python data to JSON byte string, possibly with embedded objects.
    """
    return _encoder.encode(data).encode("utf-8")


def encode(data):
    """Encode Python data to JSON string, possibly with embedded objects.
    """
    return _encoder.encode(data)


# Compatibility functions.

def dump(obj, fp):
    iterable = _encoder.iterencode(obj)
    for chunk in iterable:
        fp.write(chunk)


def dumps(obj):
    return _encoder.encode(obj)


def load(fp):
    return loads(fp.read())


def loads(s):
    return _decoder.decode(s)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
