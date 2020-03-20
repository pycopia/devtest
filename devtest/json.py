# python3

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Implementation of JSON codec for general test framework.

Basically, just pre-instantiates an encoder and decoder with options that is
common for all of the framework.

Also provides both text and bytes object codecs.

It can encode most Python objects as an embedded pickle string. Any other JSON
reader can read it, but it won't be able to decode the pickle.
"""

__all__ = ['JSONSettingsError', 'Encoder', 'Decoder', 'decode_bytes', 'decode',
           'encode_bytes', 'encode', 'dump', 'dumps', 'load', 'loads']

import json
import pickle


class JSONSettingsError(TypeError):
    pass


class Encoder(json.JSONEncoder):
    """Encodes Python objects into JSON, and provides means to encode other
    Python objects.
    """

    def __init__(self):
        super(Encoder, self).__init__(ensure_ascii=False)

    def default(self, o):
        try:
            return {"_pickle_": pickle.dumps(o, protocol=pickle.HIGHEST_PROTOCOL).hex()}
        except Exception:  # noqa
            return super().default(o)


class Decoder(json.JSONDecoder):
    """Decodes JSON into Python objects, and reconstitutes additional Python
    objects that were encoded by the encoder in this module.
    """

    def __init__(self):
        super(Decoder, self).__init__(object_hook=self._object_hook)

    def _object_hook(self, o):
        if "_pickle_" in o:
            return pickle.loads(bytes.fromhex(o["_pickle_"]))
        return o


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


def from_file(filename):
    """Read JSON from a file.

    Args:
        filename: (str) path the JSON file to read.
        """
    with open(filename, "r", encoding="utf8") as fo:
        s = fo.read()
        o = _decoder.decode(s)
    return o


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
