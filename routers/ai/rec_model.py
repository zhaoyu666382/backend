import json, torch
import torch.nn as nn
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "rec_model.pt"
META_PATH  = BASE_DIR / "rec_meta.json"

EMBED_DIM = 32
SEQ_LEN   = 10
_device   = "cuda" if torch.cuda.is_available() else "cpu"


class LightGNN(nn.Module):
    def __init__(self, num_nodes, embed_dim):
        super().__init__()
        self.embed = nn.Embedding(num_nodes, embed_dim)
        self.w1    = nn.Linear(embed_dim * 2, embed_dim)
        self.w2    = nn.Linear(embed_dim * 2, embed_dim)

    def aggregate(self, node_ids, neighbor_ids, w):
        return torch.relu(w(torch.cat(
            [self.embed(node_ids), self.embed(neighbor_ids).mean(dim=1)], dim=-1)))

    def forward(self, user_ids, item_ids, user_nb, item_nb):
        return (self.aggregate(user_ids, user_nb, self.w1),
                self.aggregate(item_ids, item_nb, self.w2))


class BehaviorTransformer(nn.Module):
    def __init__(self, item_embed, seq_len=SEQ_LEN, nhead=2, num_layers=2):
        super().__init__()
        d = item_embed.embedding_dim
        self.item_embed  = item_embed
        self.pos_embed   = nn.Embedding(seq_len, d)
        self.transformer = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(d_model=d, nhead=nhead,
                                       dim_feedforward=d*4, dropout=0.1, batch_first=True),
            num_layers=num_layers)
        self.norm = nn.LayerNorm(d)

    def forward(self, seq_ids, mask=None):
        pos = torch.arange(seq_ids.size(1), device=seq_ids.device).unsqueeze(0)
        x   = self.item_embed(seq_ids) + self.pos_embed(pos)
        return self.norm(self.transformer(x, src_key_padding_mask=mask))[:, -1, :]


class GNNTransformerRec(nn.Module):
    def __init__(self, num_users, num_items, embed_dim=EMBED_DIM):
        super().__init__()
        self.num_users      = num_users
        self.num_items      = num_items
        self.gnn            = LightGNN(num_users + num_items, embed_dim)
        self.item_embed_seq = nn.Embedding(num_items + 1, embed_dim, padding_idx=0)
        self.transformer    = BehaviorTransformer(self.item_embed_seq)
        self.predictor = nn.Sequential(
            nn.Linear(embed_dim * 3, 64), nn.ReLU(),
            nn.Dropout(0.2), nn.Linear(64, 1))

    def forward(self, user_ids, item_ids, seq_ids, u_nb, i_nb, mask=None):
        ug, ig  = self.gnn(user_ids, item_ids + self.num_users, u_nb, i_nb)
        seq_emb = self.transformer(seq_ids, mask)
        return self.predictor(torch.cat([ug, ig, seq_emb], dim=-1)).squeeze(-1)

    def batch_score(self, user_id: int, all_item_ids: list,
                    seq_tensor, mask_tensor, meta: dict) -> list:
        """
        批量计算一个用户对所有候选商品的评分（一次性推理，比逐个快10x）
        """
        n = len(all_item_ids)
        K = 5

        user_t = torch.tensor([user_id] * n, device=_device)
        item_t = torch.tensor(all_item_ids, device=_device)
        seq_t  = seq_tensor.expand(n, -1)
        mask_t = mask_tensor.expand(n, -1)
        u_nb   = torch.randint(0, self.num_items, (n, K), device=_device)
        i_nb   = torch.randint(0, self.num_users, (n, K), device=_device)

        with torch.no_grad():
            scores = self.forward(user_t, item_t, seq_t, u_nb, i_nb, mask_t)
        return scores.cpu().tolist()


_model = None
_meta  = None


def preload():
    """后端启动时调用，提前加载推荐模型"""
    global _model, _meta
    if _model is not None:
        return
    if not META_PATH.exists() or not MODEL_PATH.exists():
        print("[RecModel] 模型文件不存在，跳过预加载")
        return
    _meta  = json.loads(META_PATH.read_text(encoding="utf-8"))
    _model = GNNTransformerRec(_meta["num_users"], _meta["num_items"], EMBED_DIM)
    _model.load_state_dict(torch.load(MODEL_PATH, map_location=_device))
    _model.to(_device).eval()
    print(f"[RecModel] 预加载完成，设备={_device}")


def get_recommendations(user_id: int, recent_items: list,
                        all_item_ids: list, top_k: int = 6) -> list:
    global _model, _meta
    if _model is None:
        try:
            preload()
        except Exception:
            return []
    if _model is None:
        return []

    user_map = _meta["user_id_map"]
    item_map = _meta["item_id_map"]
    str_uid  = str(user_id)
    if str_uid not in user_map:
        return []

    model_uid = user_map[str_uid]
    seq = [item_map.get(str(i), 0) + 1 for i in recent_items[-SEQ_LEN:]]
    seq = [0] * (SEQ_LEN - len(seq)) + seq
    seq_t  = torch.tensor([seq], device=_device)
    mask_t = (seq_t == 0)

    # 过滤有效商品
    valid = [(db_id, item_map[str(db_id)])
             for db_id in all_item_ids if str(db_id) in item_map]
    if not valid:
        return []

    db_ids    = [x[0] for x in valid]
    model_ids = [x[1] for x in valid]

    # 一次批量推理，替代之前的循环
    scores = _model.batch_score(model_uid, model_ids, seq_t, mask_t, _meta)

    ranked = sorted(zip(db_ids, scores), key=lambda x: x[1], reverse=True)
    return [{"item_id": db_id, "score": round(s, 4)} for db_id, s in ranked[:top_k]]