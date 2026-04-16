"""
文件位置：backend/services/blockchain_service.py
作用：完整的本地区块链实现
  - SHA-256 哈希链
  - 区块增删查
  - 链完整性验证
  - 溯源事件锚定
"""
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings


class Block:
    """单个区块"""

    def __init__(
        self,
        index: int,
        data: Any,
        previous_hash: str,
        timestamp: Optional[float] = None,
    ):
        self.index         = index
        self.timestamp     = timestamp or time.time()
        self.data          = data
        self.previous_hash = previous_hash
        self.hash          = self._calc_hash()

    def _calc_hash(self) -> str:
        content = json.dumps({
            "index":         self.index,
            "timestamp":     self.timestamp,
            "data":          self.data,
            "previous_hash": self.previous_hash,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict:
        return {
            "index":         self.index,
            "timestamp":     self.timestamp,
            "time_str":      datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "data":          self.data,
            "previous_hash": self.previous_hash,
            "hash":          self.hash,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Block":
        b = cls(d["index"], d["data"], d["previous_hash"], d["timestamp"])
        b.hash = d["hash"]
        return b


class SimpleBlockchain:
    """本地 JSON 文件区块链"""

    CHAIN_FILE: Path = settings.BLOCKCHAIN_FILE

    # ── 内部 IO ─────────────────────────────────────────────
    def _load(self) -> List[Dict]:
        if not self.CHAIN_FILE.exists():
            return []
        try:
            return json.loads(self.CHAIN_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, chain: List[Dict]) -> None:
        self.CHAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.CHAIN_FILE.write_text(
            json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── 创世区块 ─────────────────────────────────────────────
    def _genesis(self) -> Block:
        return Block(
            index=0,
            data={"type": "GENESIS", "message": "绿色食品交易平台区块链创世区块"},
            previous_hash="0" * 64,
        )

    def _ensure_genesis(self) -> List[Dict]:
        chain = self._load()
        if not chain:
            g = self._genesis()
            chain = [g.to_dict()]
            self._save(chain)
        return chain

    # ── 核心操作 ─────────────────────────────────────────────
    def add_block(self, data: Any) -> Block:
        chain = self._ensure_genesis()
        last  = Block.from_dict(chain[-1])
        new_block = Block(
            index=last.index + 1,
            data=data,
            previous_hash=last.hash,
        )
        chain.append(new_block.to_dict())
        self._save(chain)
        return new_block

    def verify_chain(self) -> bool:
        chain = self._load()
        if not chain:
            return True
        for i in range(1, len(chain)):
            cur  = Block.from_dict(chain[i])
            prev = Block.from_dict(chain[i - 1])
            # 验证哈希链接
            if cur.previous_hash != prev.hash:
                return False
            # 验证本块哈希未被篡改
            recalc = Block(cur.index, cur.data, cur.previous_hash, cur.timestamp)
            if recalc.hash != cur.hash:
                return False
        return True

    # ── 溯源专用方法 ─────────────────────────────────────────
    def anchor(
        self,
        batch_number: str,
        event_type: str,
        location: str,
        description: str,
        operator: str = "system",
    ) -> str:
        """
        将溯源事件写入区块链，返回该区块的哈希值
        后续可在此方法中同时调用 FISCO BCOS 存证
        """
        data = {
            "type":         "TRACE_EVENT",
            "batch_number": batch_number,
            "event_type":   event_type,
            "location":     location,
            "description":  description,
            "operator":     operator,
            "timestamp":    datetime.now().isoformat(),
        }
        block = self.add_block(data)
        return block.hash

    # ── 查询方法 ─────────────────────────────────────────────
    def get_blocks_by_batch(self, batch_number: str) -> List[Dict]:
        """获取某批次的所有区块"""
        chain = self._load()
        return [
            b for b in chain
            if isinstance(b.get("data"), dict)
            and b["data"].get("batch_number") == batch_number
        ]

    def stats(self) -> Dict:
        """返回链状态摘要（供管理员端展示）"""
        chain = self._load()
        if not chain:
            return {
                "length":      0,
                "valid":       True,
                "latest_hash": None,
                "latest_time": None,
                "blocks":      [],
            }
        latest = chain[-1]
        return {
            "length":      len(chain),
            "valid":       self.verify_chain(),
            "latest_hash": latest.get("hash", ""),
            "latest_time": latest.get("time_str", ""),
            "blocks":      chain[-10:],   # 最近10个区块
        }

    def get_all_blocks(self, page: int = 1, page_size: int = 20) -> Dict:
        """分页获取全部区块（最新的在前）"""
        chain = self._load()
        total    = len(chain)
        reversed_chain = list(reversed(chain))
        start = (page - 1) * page_size
        end   = start + page_size
        return {
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "blocks":    reversed_chain[start:end],
        }


# 全局单例
blockchain = SimpleBlockchain()