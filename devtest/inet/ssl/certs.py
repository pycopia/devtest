# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Common certificate operations.
"""

from __future__ import generator_stop

import os
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate_private_key(filename, passphrase, _backend=None):
    backend = _backend or default_backend()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=backend)
    if passphrase is None:
        algo = serialization.NoEncryption()
    else:
        algo = serialization.BestAvailableEncryption(passphrase.encode("ascii"))
    key_bytes = key.private_bytes(encoding=serialization.Encoding.PEM,
                                  format=serialization.PrivateFormat.TraditionalOpenSSL,
                                  encryption_algorithm=algo)
    with open(filename, "wb") as f:
        f.write(key_bytes)
    return key


_NAME2OID = {
    "business_category": NameOID.BUSINESS_CATEGORY,
    "common_name": NameOID.COMMON_NAME,
    "country": NameOID.COUNTRY_NAME,
    "dn_qualifier": NameOID.DN_QUALIFIER,
    "domain_component": NameOID.DOMAIN_COMPONENT,
    "email": NameOID.EMAIL_ADDRESS,
    "email_address": NameOID.EMAIL_ADDRESS,
    "generation_qualifier": NameOID.GENERATION_QUALIFIER,
    "name": NameOID.GIVEN_NAME,
    "given_name": NameOID.GIVEN_NAME,
    "jurisdiction_country": NameOID.JURISDICTION_COUNTRY_NAME,
    "jurisdiction_locality": NameOID.JURISDICTION_LOCALITY_NAME,
    "jurusdiction_state": NameOID.JURISDICTION_STATE_OR_PROVINCE_NAME,
    "jurusdiction_province": NameOID.JURISDICTION_STATE_OR_PROVINCE_NAME,
    "locality": NameOID.LOCALITY_NAME,
    "organizational_unit": NameOID.ORGANIZATIONAL_UNIT_NAME,
    "organization_unit": NameOID.ORGANIZATIONAL_UNIT_NAME,
    "organization": NameOID.ORGANIZATION_NAME,
    "pseudonym": NameOID.PSEUDONYM,
    "serial_number": NameOID.SERIAL_NUMBER,
    "state": NameOID.STATE_OR_PROVINCE_NAME,
    "province": NameOID.STATE_OR_PROVINCE_NAME,
    "surname": NameOID.SURNAME,
    "title": NameOID.TITLE,
}


def _convert_attributes(subject_dict: dict) -> list:
    converted = []
    for keyname, oid in _NAME2OID.items():
        value = subject_dict.get(keyname)
        if value:
            converted.append(x509.NameAttribute(oid, value))
    return converted


def generate_certificate_request(common_name,
                                 country=None,
                                 state=None,
                                 locality=None,
                                 organization=None,
                                 organization_unit=None,
                                 email=None,
                                 passphrase=None,
                                 _backend=None):
    attribs = {
        "common_name": common_name,
        "country": country,
        "state": state,
        "locality": locality,
        "organization": organization,
        "organization_unit": organization_unit,
        "email": email,
    }
    backend = _backend or default_backend()

    private_key = generate_private_key(common_name + ".key", passphrase, backend)

    builder = x509.CertificateSigningRequestBuilder()

    builder = builder.subject_name(x509.Name(_convert_attributes(attribs)))
    builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None),
                                    critical=True)
    builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]),
                                    critical=True)

    request = builder.sign(private_key, hashes.SHA256(), backend)

    with open(common_name + ".csr.pem", "wb") as fo:
        fo.write(request.public_bytes(serialization.Encoding.PEM))
    return private_key, request


def generate_self_signed_certificate(common_name,
                                     country=None,
                                     state=None,
                                     locality=None,
                                     organization=None,
                                     organization_unit=None,
                                     email=None,
                                     passphrase=None):
    backend = default_backend()
    key, csr = generate_certificate_request(common_name,
                                            country=country,
                                            state=state,
                                            locality=locality,
                                            organization=organization,
                                            organization_unit=organization_unit,
                                            email=email,
                                            passphrase=passphrase,
                                            _backend=backend)

    issuer = subject = csr.subject
    not_before = datetime.now()
    not_after = not_before + timedelta(days=365)
    builder = x509.CertificateBuilder(issuer_name=issuer,
                                      subject_name=subject,
                                      public_key=csr.public_key(),
                                      serial_number=1,
                                      not_valid_before=not_before,
                                      not_valid_after=not_after,
                                      extensions=csr.extensions)

    cert = builder.sign(key, hashes.SHA256(), backend)
    with open(common_name + ".crt.pem", "wb") as fo:
        fo.write(cert.public_bytes(serialization.Encoding.PEM))
    return cert


def cert_exists(host):
    return (os.path.exists("{}.crt.pem".format(host)) and os.path.exists("{}.key".format(host)))


if __name__ == "__main__":
    import sys
    CN = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    cert = generate_self_signed_certificate(CN,
                                            country="US",
                                            state="California",
                                            locality="Santa Clara",
                                            organization="Acme",
                                            organization_unit="Eng",
                                            passphrase=None)
    print("See: {}.crt.pem".format(CN))

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
