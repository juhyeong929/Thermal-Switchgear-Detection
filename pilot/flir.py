"""FLIR E8 radiometric JPEG reader.

이동형 열화상 JPEG의 APP1(FLIR) 세그먼트에서 다음을 꺼낸다.
  - 16-bit raw thermal (320x240)
  - Planck 상수 및 촬영 파라미터
  - 내장 실화상 (640x480)
그리고 raw -> 섭씨 온도로 변환한다.

원본 파일은 열기만 하며 절대 수정하지 않는다.
"""
from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass

import numpy as np
from PIL import Image

# FLIR FFF record types
REC_RAW = 1        # RawData (16-bit thermal, PNG-encoded)
REC_EMBEDDED = 14  # 내장 실화상 JPEG
REC_CAMERA = 32    # CameraInfo (Planck 상수, 카메라 모델)
REC_PARAMS = 42    # Real2IR / Offset (실화상-열화상 정합 파라미터)

# CameraInfo 레코드 내 오프셋 (exiftool FLIR.pm 기준, little-endian float)
_OFF = {
    "emissivity": 0x20, "distance": 0x24, "refl_temp": 0x28,
    "planck_R1": 0x58, "planck_B": 0x5C, "planck_F": 0x60,
    "planck_O": 0x308, "planck_R2": 0x30C, "fov": 0x1B4,
}
_STR = {"model": 0xD4, "serial": 0x104, "software": 0x114, "lens": 0x170}


@dataclass
class FlirMeta:
    model: str
    serial: str
    lens: str
    fov: float
    emissivity: float
    distance: float
    refl_temp: float          # Kelvin
    planck: tuple             # (R1, B, F, O, R2)
    real2ir: float
    offset: tuple             # (OffsetX, OffsetY) in IR px


def _app1_payload(blob: bytes) -> bytes:
    """FLIR APP1 청크들을 순서대로 이어붙여 FFF 컨테이너를 복원한다."""
    i, chunks = 2, {}
    while i < len(blob) - 1 and blob[i] == 0xFF:
        marker = blob[i + 1]
        if marker == 0xD8:
            i += 2
            continue
        seg_len = struct.unpack(">H", blob[i + 2:i + 4])[0]
        seg = blob[i + 4:i + 2 + seg_len]
        if marker == 0xE1 and seg.startswith(b"FLIR\x00"):
            chunks[seg[6]] = seg[8:]
        if marker == 0xDA:
            break
        i += 2 + seg_len
    if not chunks:
        raise ValueError("FLIR APP1 세그먼트 없음 (방사 데이터 미포함 파일)")
    return b"".join(chunks[k] for k in sorted(chunks))


def _records(fff: bytes) -> dict:
    """FFF 인덱스는 big-endian, 레코드 내부 값은 little-endian."""
    if fff[:4] != b"FFF\x00":
        raise ValueError("FFF 헤더 아님")
    index_off = struct.unpack(">I", fff[0x18:0x1C])[0]
    count = struct.unpack(">I", fff[0x1C:0x20])[0]
    out = {}
    for n in range(count):
        o = index_off + n * 32
        rec_type, _sub, _ver, _idx, data_off, data_len = struct.unpack(">HHIIII", fff[o:o + 20])
        if data_len:
            out.setdefault(rec_type, fff[data_off:data_off + data_len])
    return out


def _f32(b, o): return struct.unpack("<f", b[o:o + 4])[0]
def _i32(b, o): return struct.unpack("<i", b[o:o + 4])[0]
def _txt(b, o, n=32): return b[o:o + n].split(b"\x00")[0].decode("latin1")


def read(path) -> tuple[np.ndarray, np.ndarray, FlirMeta]:
    """반환: (온도맵 °C float32 [240,320], 실화상 RGB uint8 [480,640,3], 메타)"""
    with open(path, "rb") as fh:
        blob = fh.read()
    recs = _records(_app1_payload(blob))

    cam = recs[REC_CAMERA]
    meta = FlirMeta(
        model=_txt(cam, _STR["model"]), serial=_txt(cam, _STR["serial"]),
        lens=_txt(cam, _STR["lens"]), fov=_f32(cam, _OFF["fov"]),
        emissivity=_f32(cam, _OFF["emissivity"]), distance=_f32(cam, _OFF["distance"]),
        refl_temp=_f32(cam, _OFF["refl_temp"]),
        planck=(_f32(cam, _OFF["planck_R1"]), _f32(cam, _OFF["planck_B"]),
                _f32(cam, _OFF["planck_F"]), _i32(cam, _OFF["planck_O"]),
                _f32(cam, _OFF["planck_R2"])),
        real2ir=_f32(recs[REC_PARAMS], 0),
        offset=struct.unpack("<hh", recs[REC_PARAMS][4:8]),
    )

    raw_blob = recs[REC_RAW]
    p = raw_blob.find(b"\x89PNG")
    raw = np.array(Image.open(io.BytesIO(raw_blob[p:]))).astype("<u2")
    if raw.max() > 30000:                      # FLIR은 바이트 스왑된 상태로 저장한다
        raw = raw.byteswap()

    vis_blob = recs[REC_EMBEDDED]
    q = vis_blob.find(b"\xff\xd8\xff")
    visual = np.array(Image.open(io.BytesIO(vis_blob[q:])).convert("RGB"))

    return raw_to_celsius(raw, meta), visual, meta


def raw_to_celsius(raw: np.ndarray, meta: FlirMeta) -> np.ndarray:
    """Planck 역변환. 대기 감쇠는 무시한다 (거리 1 m 고정 촬영이라 영향이 미미)."""
    R1, B, F, O, R2 = meta.planck
    E = meta.emissivity
    raw_refl = R1 / (R2 * (math.exp(B / meta.refl_temp) - F)) - O
    raw_obj = (raw.astype(np.float64) - (1.0 - E) * raw_refl) / E
    with np.errstate(divide="ignore", invalid="ignore"):
        temp = B / np.log(R1 / (R2 * (raw_obj + O)) + F) - 273.15
    return temp.astype(np.float32)


def read_lepton(path) -> np.ndarray:
    """고정형 Lepton TIFF: 화소값이 centi-Kelvin이다."""
    return np.array(Image.open(path)).astype(np.float32) / 100.0 - 273.15
