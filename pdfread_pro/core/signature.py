"""Đọc và kiểm tra chữ ký số PDF (PKCS#7/CMS) bằng bộ đọc DER tự viết.

Kiểm tra: băm lại vùng ByteRange và so với messageDigest trong chữ ký; vùng ký có phủ
tới cuối file hay không (sửa sau khi ký). KHÔNG kiểm tra độ tin cậy chứng thư (CA).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

_BYTERANGE = re.compile(rb"/ByteRange\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\]")
_PDF_DATE = re.compile(rb"/M\s*\(D:(\d{14})([+\-Z])?(\d\d)?'?(\d\d)?")

_HASHES = {
    "1.3.14.3.2.26": "sha1",
    "2.16.840.1.101.3.4.2.1": "sha256",
    "2.16.840.1.101.3.4.2.2": "sha384",
    "2.16.840.1.101.3.4.2.3": "sha512",
    "2.16.840.1.101.3.4.2.4": "sha224",
    "1.2.840.113549.2.5": "md5",
}
_OID_MSG_DIGEST = "1.2.840.113549.1.9.4"
_OID_SIGNING_TIME = "1.2.840.113549.1.9.5"
_OID_CN = "2.5.4.3"


class _N:
    __slots__ = ("b", "tag", "s", "e", "hs", "ne")

    def __init__(self, b, tag, s, e, hs, ne):
        self.b, self.tag, self.s, self.e, self.hs, self.ne = b, tag, s, e, hs, ne

    @property
    def value(self) -> bytes:
        return self.b[self.s:self.e]

    @property
    def raw(self) -> bytes:
        return self.b[self.hs:self.ne]


def _parse(b: bytes, pos: int, limit: int) -> _N:
    if pos + 2 > limit:
        raise ValueError("DER cụt")
    hs = pos
    tag = b[pos]
    ln = b[pos + 1]
    pos += 2
    if ln & 0x80:
        n = ln & 0x7F
        if n == 0:  # độ dài không xác định (BER)
            s = p = pos
            while not (p + 1 < limit and b[p] == 0 and b[p + 1] == 0):
                p = _parse(b, p, limit).ne
            return _N(b, tag, s, p, hs, p + 2)
        ln = int.from_bytes(b[pos:pos + n], "big")
        pos += n
    if pos + ln > limit:
        raise ValueError("DER vượt giới hạn")
    return _N(b, tag, pos, pos + ln, hs, pos + ln)


def _kids(n: _N) -> List[_N]:
    out, p = [], n.s
    while p < n.e:
        c = _parse(n.b, p, n.e)
        out.append(c)
        p = c.ne
    return out


def _oid(n: _N) -> str:
    v = n.value
    if not v:
        return ""
    parts = [str(v[0] // 40), str(v[0] % 40)]
    acc = 0
    for x in v[1:]:
        acc = (acc << 7) | (x & 0x7F)
        if not x & 0x80:
            parts.append(str(acc))
            acc = 0
    return ".".join(parts)


def _decode_str(n: _N) -> str:
    v = n.value
    if n.tag == 0x1E:
        return v.decode("utf-16-be", "replace")
    try:
        return v.decode("utf-8")
    except UnicodeDecodeError:
        return v.decode("latin-1")


def _parse_time(n: _N) -> Optional[datetime]:
    s = n.value.decode("ascii", "ignore").rstrip("Z")
    try:
        if n.tag == 0x17:  # UTCTime
            yy = int(s[:2])
            year = 2000 + yy if yy < 50 else 1900 + yy
            s = f"{year}{s[2:]}"
        dt = datetime.strptime(s[:14].ljust(14, "0"), "%Y%m%d%H%M%S")
        return dt.replace(tzinfo=timezone.utc).astimezone()
    except Exception:
        return None


def _cert_info(cert: _N):
    """(issuer_raw, serial_raw, subject_cn)"""
    tbs = _kids(cert)[0]
    k = _kids(tbs)
    i = 1 if k[0].tag == 0xA0 else 0
    serial, issuer, subject = k[i], k[i + 2], k[i + 4]
    cn = ""
    for rdn in _kids(subject):
        for atv in _kids(rdn):
            a = _kids(atv)
            if len(a) == 2 and _oid(a[0]) == _OID_CN:
                cn = _decode_str(a[1])
    return issuer.raw, serial.raw, cn


@dataclass
class SigInfo:
    digest_ok: Optional[bool] = None     # None = không xác định được
    covers_end: bool = True
    signer: str = ""
    time: Optional[datetime] = None
    end: int = 0                          # c + d


def _parse_cms(blob: bytes):
    """Trả về (digest_alg, message_digest, signer_name, signing_time)."""
    root = _parse(blob, 0, len(blob))
    ci = _kids(root)
    sd = _kids(ci[1])[0]
    k = _kids(sd)
    certs, signer_infos = [], None
    for c in k[3:]:
        if c.tag == 0xA0:
            certs = _kids(c)
        elif c.tag == 0x31:
            signer_infos = c
    si = _kids(_kids(signer_infos)[0])
    sid, dig_alg = si[1], si[2]
    algo = _HASHES.get(_oid(_kids(dig_alg)[0]), "")
    msg_digest, stime = None, None
    for c in si[3:]:
        if c.tag == 0xA0:  # signedAttrs
            for attr in _kids(c):
                a = _kids(attr)
                o = _oid(a[0])
                val = _kids(a[1])[0]
                if o == _OID_MSG_DIGEST:
                    msg_digest = val.value
                elif o == _OID_SIGNING_TIME:
                    stime = _parse_time(val)
            break
    signer = ""
    try:
        sk = _kids(sid) if sid.tag == 0x30 else []
        want = (sk[0].raw, sk[1].raw) if len(sk) == 2 else None
        first_cn = ""
        for cert in certs:
            issuer, serial, cn = _cert_info(cert)
            first_cn = first_cn or cn
            if want and (issuer, serial) == want:
                signer = cn
                break
        signer = signer or first_cn
    except Exception:
        pass
    return algo, msg_digest, signer, stime


def _pdf_date(window: bytes) -> Optional[datetime]:
    m = _PDF_DATE.search(window)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1).decode(), "%Y%m%d%H%M%S")
        sign, hh, mm = m.group(2), m.group(3), m.group(4)
        if sign in (b"+", b"-"):
            off = int(hh or 0) * 60 + int(mm or 0)
            from datetime import timedelta
            tz = timezone(timedelta(minutes=off if sign == b"+" else -off))
            return dt.replace(tzinfo=tz).astimezone()
        if sign == b"Z":
            return dt.replace(tzinfo=timezone.utc).astimezone()
        return dt.astimezone()
    except Exception:
        return None


def inspect_signatures(data: bytes) -> List[SigInfo]:
    """Danh sách chữ ký trong file (rỗng nếu không có). Ném ValueError nếu hỏng cấu trúc."""
    sigs: List[SigInfo] = []
    if b"/ByteRange" not in data:
        return sigs
    n = len(data)
    for m in _BYTERANGE.finditer(data):
        a, b, c, d = (int(x) for x in m.groups())
        si = SigInfo(end=c + d)
        if a != 0 or a + b > c or c + d > n or b < 0 or d < 0:
            si.digest_ok = False
            si.covers_end = False
            sigs.append(si)
            continue
        raw = data[a + b:c].strip()
        if raw[:1] == b"<":
            raw = raw[1:]
        if raw[-1:] == b">":
            raw = raw[:-1]
        try:
            blob = bytes.fromhex(raw.decode("ascii"))
            algo, md, signer, stime = _parse_cms(blob)
            si.signer, si.time = signer, stime
            if algo and md is not None:
                h = hashlib.new(algo)
                h.update(data[a:a + b])
                h.update(data[c:c + d])
                si.digest_ok = h.digest() == md
        except Exception:
            si.digest_ok = None
        if si.time is None:
            si.time = (_pdf_date(data[max(0, m.start() - 600):m.end() + 600])
                       or _pdf_date(data[c:c + 800]))   # /M thường nằm sau /Contents
        sigs.append(si)
    if sigs:
        last_end = max(s.end for s in sigs)
        tail = data[last_end:]
        covers = not tail.strip(b"\r\n \t\x00")
        for s in sigs:
            s.covers_end = covers if s.end == last_end else True
    return sigs


def summarize(sigs: List[SigInfo]):
    """(status, signers_unique, latest_time) cho cả file."""
    if not sigs:
        return "none", [], None
    if any(s.digest_ok is None for s in sigs):
        status = "unreadable"
    elif any(s.digest_ok is False for s in sigs):
        status = "broken"
    elif any(not s.covers_end for s in sigs):
        status = "modified"
    else:
        status = "ok"
    signers: List[str] = []
    for s in sigs:
        if s.signer and s.signer not in signers:
            signers.append(s.signer)
    times = [s.time for s in sigs if s.time]
    return status, signers, (max(times) if times else None)
