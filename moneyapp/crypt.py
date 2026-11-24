"""Password encryption for backups, using only the Python standard library.

- The password becomes keys with scrypt (hashlib.scrypt): slow on purpose, so guessing
  passwords is expensive. A fresh random salt for every backup.
- The data is encrypted with ChaCha20 (RFC 8439, the cipher TLS and WireGuard use),
  written out here because the standard library has no cipher; it's checked against the
  RFC's own test vectors (tests/test_app.py).
- Encrypt-then-MAC: HMAC-SHA256 over the header and the encrypted data, checked in
  constant time before anything is decrypted. A wrong password or a changed byte is
  refused, never half-read.

File layout: MAGIC | scrypt n, r, p (3 x 4 bytes) | salt (16) | nonce (12) | data | tag (32).
"""

import hashlib
import hmac
import os
import struct

from .store import ApiError

MAGIC = b"HLEDGER-ENC1\n"
N, R, P = 2 ** 15, 8, 1           # scrypt cost: ~32 MiB of memory, a fraction of a second
_HEAD = len(MAGIC) + 12 + 16 + 12
_MASK = 0xFFFFFFFF


def _rotl(v, c):
    return ((v << c) & _MASK) | (v >> (32 - c))


def _block(key_words, counter, nonce_words):
    """One 64-byte ChaCha20 block (RFC 8439 section 2.3)."""
    s = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *key_words, counter & _MASK, *nonce_words]
    x = s[:]
    for _ in range(10):
        for a, b, c, d in ((0, 4, 8, 12), (1, 5, 9, 13), (2, 6, 10, 14), (3, 7, 11, 15),
                           (0, 5, 10, 15), (1, 6, 11, 12), (2, 7, 8, 13), (3, 4, 9, 14)):
            x[a] = (x[a] + x[b]) & _MASK; x[d] = _rotl(x[d] ^ x[a], 16)
            x[c] = (x[c] + x[d]) & _MASK; x[b] = _rotl(x[b] ^ x[c], 12)
            x[a] = (x[a] + x[b]) & _MASK; x[d] = _rotl(x[d] ^ x[a], 8)
            x[c] = (x[c] + x[d]) & _MASK; x[b] = _rotl(x[b] ^ x[c], 7)
    return struct.pack("<16I", *((x[i] + s[i]) & _MASK for i in range(16)))


def chacha20(key, nonce, data, counter=1):
    """Encrypt or decrypt (the same operation) with ChaCha20 (RFC 8439 section 2.4)."""
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError("ChaCha20 needs a 32-byte key and a 12-byte nonce")
    kw, nw = struct.unpack("<8I", key), struct.unpack("<3I", nonce)
    stream = b"".join(_block(kw, counter + i, nw) for i in range((len(data) + 63) // 64))
    n = len(data)
    return (int.from_bytes(data, "little") ^ int.from_bytes(stream[:n], "little")).to_bytes(n, "little") if n else b""


def _keys(password, salt, n, r, p):
    if not password:
        raise ApiError("A backup password is needed")
    k = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=128 * 1024 * 1024, dklen=64)
    return k[:32], k[32:]


def is_encrypted(blob):
    return blob[:len(MAGIC)] == MAGIC


def encrypt(data, password):
    salt, nonce = os.urandom(16), os.urandom(12)
    enc_key, mac_key = _keys(password, salt, N, R, P)
    head = MAGIC + struct.pack(">III", N, R, P) + salt + nonce
    body = chacha20(enc_key, nonce, data)
    return head + body + hmac.new(mac_key, head + body, hashlib.sha256).digest()


def decrypt(blob, password):
    """The original bytes, or ApiError when the password is wrong or the file was changed."""
    if not is_encrypted(blob) or len(blob) < _HEAD + 32:
        raise ApiError("That isn't an encrypted MoneyThistle backup")
    n, r, p = struct.unpack(">III", blob[len(MAGIC):len(MAGIC) + 12])
    if n > 2 ** 20 or r > 32 or p > 16:
        raise ApiError("That backup asks for unreasonable key settings")
    salt = blob[len(MAGIC) + 12:len(MAGIC) + 28]
    nonce = blob[len(MAGIC) + 28:_HEAD]
    head, body, tag = blob[:_HEAD], blob[_HEAD:-32], blob[-32:]
    enc_key, mac_key = _keys(password, salt, n, r, p)
    if not hmac.compare_digest(tag, hmac.new(mac_key, head + body, hashlib.sha256).digest()):
        raise ApiError("Wrong backup password, or the backup file was changed or damaged")
    return chacha20(enc_key, nonce, body)
