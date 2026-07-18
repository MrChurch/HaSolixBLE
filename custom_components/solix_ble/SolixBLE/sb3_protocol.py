"""Solarbank 3 A17C5 forensic handshake support.

Stops at the session-bound 4022 boundary and exports an exact transcript.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from enum import Enum
import json
import time
from pathlib import Path
from typing import Any

SB3_4001=bytes.fromhex("ff09220003000140010a824f0bbd508bb2178c3054ae2df691dab7ce7dd037c5e38b")
SB3_4003=bytes.fromhex("ff09290003000140030a824e0bbd508bb25db5286d496f964ade328b233f57fcf51eb1f2639d69c6f9")
SB3_4029=bytes.fromhex("ff094a0003000140290a824e0bbd508b9acc816cf1285604b0b741b6b202d4f3b4c28ad6630662ca07b3fef57148a0835a890e253dcdeaf36c2a4ca1d6229283bc963af531b711fd239a")
SB3_4005=bytes.fromhex("ff092f0003000140050a824e0bbd508bb25db5286d496f9670823925d138f20cc16133c3ead23c3a1da7e14615bdb8")
SB3_4021=bytes.fromhex("ff095c0003000140210ac6acb7576d319c3fa39072ab14c59b8ad8a9898e878cd247a9fc52db2ae237f48ff72be8561f4f2719d194d5536cbb8cdf939506ad84e2fc2ef336cb18891400506d6aadc329ea1011433c2e3d5f8071ec20")

class SB3State(str,Enum):
    IDLE="idle"; WAIT_4801="wait_4801"; WAIT_4803="wait_4803"; WAIT_4829="wait_4829"; WAIT_4805="wait_4805"; WAIT_4821="wait_4821"; NEED_DYNAMIC_4022="need_dynamic_4022"; FAILED="failed"

def xor_checksum(data:bytes)->bytes:
    value=0
    for b in data: value ^= b
    return bytes([value])

@dataclass(slots=True)
class SB3Packet:
    raw:bytes; pattern:bytes; command:bytes; payload:bytes
    @property
    def command_hex(self)->str: return self.command.hex()

def parse_packet(packet:bytes)->SB3Packet:
    if len(packet)<10 or packet[:2]!=b"\xff\x09": raise ValueError("invalid FF09 packet")
    if int.from_bytes(packet[2:4],"little")!=len(packet): raise ValueError("length mismatch")
    if packet[-1:]!=xor_checksum(packet[:-1]): raise ValueError("checksum mismatch")
    return SB3Packet(packet,packet[4:7],packet[7:9],packet[9:-1])

@dataclass(slots=True)
class SB3Transcript:
    device_name:str; address:str; started:float=field(default_factory=time.monotonic); events:list[dict[str,Any]]=field(default_factory=list)
    def add(self,direction:str,packet:bytes,note:str="")->None:
        p=parse_packet(packet)
        self.events.append({"t":round(time.monotonic()-self.started,6),"direction":direction,"pattern":p.pattern.hex(),"command":p.command.hex(),"payload":p.payload.hex(),"packet":packet.hex(),"note":note})
    async def export(self,directory:str|Path="/config")->Path:
        """Write the transcript outside Home Assistant's event loop."""
        return await asyncio.to_thread(self._export_sync, directory)

    def _export_sync(self,directory:str|Path)->Path:
        d=Path(directory); d.mkdir(parents=True,exist_ok=True)
        path=d/f"solix_sb3_transcript_{self.address.replace(':','')}_{int(time.time())}.json"
        path.write_text(json.dumps({"device_name":self.device_name,"address":self.address,"events":self.events},indent=2),encoding="utf-8")
        return path

class SB3Handshake:
    def __init__(self,device_name:str,address:str)->None:
        self.state=SB3State.IDLE; self.transcript=SB3Transcript(device_name,address); self.last_4821_payload:bytes|None=None
    def start(self)->bytes:
        if self.state is not SB3State.IDLE: raise RuntimeError(f"already started: {self.state}")
        self.state=SB3State.WAIT_4801; self.transcript.add("tx",SB3_4001,"stable negotiation start"); return SB3_4001
    def receive(self,packet:bytes)->bytes|None:
        p=parse_packet(packet); self.transcript.add("rx",packet)
        expected={SB3State.WAIT_4801:"4801",SB3State.WAIT_4803:"4803",SB3State.WAIT_4829:"4829",SB3State.WAIT_4805:"4805",SB3State.WAIT_4821:"4821"}.get(self.state)
        if expected is None or p.command_hex!=expected:
            self.state=SB3State.FAILED; raise ValueError(f"expected {expected}, got {p.command_hex}")
        if self.state is SB3State.WAIT_4801: self.state=SB3State.WAIT_4803; reply=SB3_4003
        elif self.state is SB3State.WAIT_4803: self.state=SB3State.WAIT_4829; reply=SB3_4029
        elif self.state is SB3State.WAIT_4829: self.state=SB3State.WAIT_4805; reply=SB3_4005
        elif self.state is SB3State.WAIT_4805: self.state=SB3State.WAIT_4821; reply=SB3_4021
        else:
            self.last_4821_payload=p.payload; self.state=SB3State.NEED_DYNAMIC_4022; return None
        self.transcript.add("tx",reply); return reply
    @property
    def needs_dynamic_4022(self)->bool: return self.state is SB3State.NEED_DYNAMIC_4022
