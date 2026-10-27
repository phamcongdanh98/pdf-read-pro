"""CHỈ ĐỂ TEST: gắn 1 "chữ ký số" GIẢ LẬP vào PDF – đúng cấu trúc PDF (/ByteRange + /Contents CMS có messageDigest
khớp vùng ký) để app nhận là “có chữ ký số”, nhưng KHÔNG có chữ ký RSA thật, KHÔNG có giá trị pháp lý.

Dùng:  py tests\\make_signed_sample.py <file_vao.pdf> <file_ra.pdf> [tên người ký]
"""
from __future__ import annotations

import hashlib
import re
import sys

import pikepdf

PLACE = 8192                          # số byte dành cho CMS (hex = 2×)


def _der(tag: int, body: bytes) -> bytes:
    n = len(body)
    if n < 0x80:
        ln = bytes([n])
    else:
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        ln = bytes([0x80 | len(b)]) + b
    return bytes([tag]) + ln + body


def _oid(s: str) -> bytes:
    p = [int(x) for x in s.split(".")]
    out = bytearray([p[0] * 40 + p[1]])
    for v in p[2:]:
        chunk = [v & 0x7F]
        v >>= 7
        while v:
            chunk.append(0x80 | (v & 0x7F))
            v >>= 7
        out += bytes(reversed(chunk))
    return _der(0x06, bytes(out))


def _seq(*xs: bytes) -> bytes:
    return _der(0x30, b"".join(xs))


def _set(*xs: bytes) -> bytes:
    return _der(0x31, b"".join(xs))


def _name(cn: str) -> bytes:
    return _seq(_set(_seq(_oid("2.5.4.3"), _der(0x0C, cn.encode("utf-8")))))


def _cms(digest: bytes, signer: str) -> bytes:
    serial = _der(0x02, b"\x01\x23")
    sha256 = _seq(_oid("2.16.840.1.101.3.4.2.1"), b"\x05\x00")
    issuer = _name("TEST CA - KHONG CO GIA TRI")
    tbs = _seq(_der(0xA0, _der(0x02, b"\x02")), serial, _seq(_oid("1.2.840.113549.1.1.11")), issuer,
               _seq(_der(0x17, b"260101000000Z"), _der(0x17, b"360101000000Z")), _name(signer), _seq())
    cert = _seq(tbs, _seq(_oid("1.2.840.113549.1.1.11")), _der(0x03, b"\x00"))
    attrs = _der(0xA0, _seq(_oid("1.2.840.113549.1.9.4"), _set(_der(0x04, digest)))
                 + _seq(_oid("1.2.840.113549.1.9.5"), _set(_der(0x17, b"261027120000Z"))))
    signer_info = _seq(_der(0x02, b"\x01"), _seq(issuer, serial), sha256, attrs,
                       _seq(_oid("1.2.840.113549.1.1.1")), _der(0x04, b"\x00" * 16))
    sd = _seq(_der(0x02, b"\x01"), _set(sha256), _seq(_oid("1.2.840.113549.1.7.1")), _der(0xA0, cert),
              _set(signer_info))
    return _seq(_oid("1.2.840.113549.1.7.2"), _der(0xA0, sd))


def sign_pdf(src: str, dst: str, signer: str = "TEST - CHU KY GIA LAP") -> str:
    with pikepdf.open(src) as pdf:
        sig = pikepdf.Dictionary(Type=pikepdf.Name.Sig, Filter=pikepdf.Name("/Adobe.PPKLite"),
                                 SubFilter=pikepdf.Name("/adbe.pkcs7.detached"),
                                 ByteRange=pikepdf.Array([0, 9999999999, 9999999999, 9999999999]),
                                 Contents=pikepdf.String(b"\x00" * PLACE), M=pikepdf.String("D:20261027120000+07'00'"))
        pdf.Root.TestSig = pdf.make_indirect(sig)
        pdf.save(dst, compress_streams=False, object_stream_mode=pikepdf.ObjectStreamMode.disable)
    with open(dst, "rb") as fh:
        data = bytearray(fh.read())
    m = re.search(rb"/Contents\s*<", data)
    b = m.end() - 1                                        # vị trí '<'
    c = data.index(b">", b) + 1
    br = re.search(rb"/ByteRange\s*\[[^\]]*\]", data)
    width = br.end() - br.start()                          # giữ nguyên độ dài → vị trí b, c không đổi
    new_br = f"/ByteRange [0 {b} {c} {len(data) - c}".encode().ljust(width - 1, b" ") + b"]"
    assert len(new_br) == width
    data[br.start():br.end()] = new_br
    h = hashlib.sha256(bytes(data[:b]) + bytes(data[c:])).digest()
    hexs = _cms(h, signer).hex().encode()
    assert len(hexs) <= (c - b - 2)
    data[b + 1:c - 1] = hexs.ljust(c - b - 2, b"0")
    with open(dst, "wb") as fh:
        fh.write(bytes(data))
    return dst


if __name__ == "__main__":
    sign_pdf(sys.argv[1], sys.argv[2], *(sys.argv[3:4] or []))
    print("đã tạo", sys.argv[2])
