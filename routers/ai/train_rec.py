"""
文件位置：backend/ai/train_rec.py
运行方式：cd backend && python ai/train_rec.py
"""
import json, sqlite3, random, time, torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import Dataset, DataLoader

from rec_model import GNNTransformerRec, EMBED_DIM, SEQ_LEN, BASE_DIR

DB_PATH    = r"C:\Users\123\OneDrive\桌面\backend\ai\data\green_food.db"
MODEL_SAVE = BASE_DIR / "rec_model.pt"
META_SAVE  = BASE_DIR / "rec_meta.json"
LOG_SAVE   = BASE_DIR / "rec_train_log.json"

BATCH_SIZE = 16
EPOCHS     = 80
LR         = 5e-4
NEG_RATIO  = 3
K_NEIGHBOR = 5
DEVICE     = "cuda" if torch.cuda.is_available() else "cpu"

print(f"[配置] 设备={DEVICE}  DB={DB_PATH}")

# ── 从数据库读取数据 ──────────────────────────────────────
conn = sqlite3.connect(str(DB_PATH))
user_db_ids = [r[0] for r in conn.execute(
    "SELECT id FROM users").fetchall()]
item_db_ids = [r[0] for r in conn.execute(
    "SELECT id FROM products WHERE is_active=1").fetchall()]
views_raw = conn.execute(
    "SELECT user_id, product_id FROM product_views ORDER BY viewed_at ASC").fetchall()
purchases_raw = conn.execute(
    "SELECT o.user_id, oi.product_id FROM order_items oi "
    "JOIN orders o ON o.id=oi.order_id WHERE o.status NOT IN ('cancelled')").fetchall()
conn.close()

print(f"用户={len(user_db_ids)}  商品={len(item_db_ids)}  "
      f"浏览={len(views_raw)}  购买={len(purchases_raw)}")

all_interactions = list(set(views_raw) | set(purchases_raw))

# 数据量不足时自动生成模拟数据
if len(all_interactions) < 30:
    print("数据不足，自动生成模拟交互数据...")
    random.seed(42)
    synthetic = []
    for uid in user_db_ids:
        k = random.randint(5, min(10, len(item_db_ids)))
        for iid in random.sample(item_db_ids, k):
            synthetic.append((uid, iid))
    all_interactions = list(set(all_interactions) | set(synthetic))
    print(f"生成后共 {len(all_interactions)} 条")

# ── 构建 ID 映射 ──────────────────────────────────────────
user_id_map = {db_id: idx for idx, db_id in enumerate(user_db_ids)}
item_id_map = {db_id: idx for idx, db_id in enumerate(item_db_ids)}
num_users, num_items = len(user_id_map), len(item_id_map)

user_neighbors = {i: [] for i in range(num_users)}
item_neighbors = {i: [] for i in range(num_items)}
user_seq       = {i: [] for i in range(num_users)}
pos_set        = set()

for db_uid, db_iid in all_interactions:
    if db_uid in user_id_map and db_iid in item_id_map:
        uid, iid = user_id_map[db_uid], item_id_map[db_iid]
        user_neighbors[uid].append(iid)
        item_neighbors[iid].append(uid)
        pos_set.add((uid, iid))

for db_uid, db_iid in (views_raw + purchases_raw):
    if db_uid in user_id_map and db_iid in item_id_map:
        user_seq[user_id_map[db_uid]].append(item_id_map[db_iid] + 1)

META_SAVE.write_text(json.dumps({
    "num_users":   num_users,
    "num_items":   num_items,
    "user_id_map": {str(k): v for k, v in user_id_map.items()},
    "item_id_map": {str(k): v for k, v in item_id_map.items()},
}, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"映射完成：{num_users} 用户  {num_items} 商品  {len(pos_set)} 正样本")

# ── Dataset ───────────────────────────────────────────────
def get_seq(uid):
    seq = user_seq.get(uid, [])[-SEQ_LEN:]
    pad = [0] * (SEQ_LEN - len(seq)) + seq
    msk = [True] * (SEQ_LEN - len(seq)) + [False] * len(seq)
    return pad, msk

def sample_nb(node_id, nb_list, k, max_n):
    if not nb_list:
        return [random.randint(0, max_n - 1) for _ in range(k)]
    return random.choices(nb_list, k=k)

class RecDataset(Dataset):
    def __init__(self):
        self.samples = []
        pos_list = list(pos_set)
        for uid, iid in pos_list:
            self.samples.append((uid, iid, 1.0))
        all_items = list(range(num_items))
        for uid, _ in pos_list:
            for _ in range(NEG_RATIO):
                neg = random.choice(all_items)
                while (uid, neg) in pos_set:
                    neg = random.choice(all_items)
                self.samples.append((uid, neg, 0.0))
        random.shuffle(self.samples)
        print(f"Dataset: {len(self.samples)} 条（正:{len(pos_list)} 负:{len(self.samples)-len(pos_list)}）")

    def __len__(self): return len(self.samples)

    def __getitem__(self, idx):
        uid, iid, label = self.samples[idx]
        seq, mask = get_seq(uid)
        return {
            "user_id":     torch.tensor(uid,   dtype=torch.long),
            "item_id":     torch.tensor(iid,   dtype=torch.long),
            "seq":         torch.tensor(seq,   dtype=torch.long),
            "mask":        torch.tensor(mask,  dtype=torch.bool),
            "u_neighbors": torch.tensor(sample_nb(uid, user_neighbors[uid], K_NEIGHBOR, num_items), dtype=torch.long),
            "i_neighbors": torch.tensor(sample_nb(iid, item_neighbors[iid], K_NEIGHBOR, num_users), dtype=torch.long),
            "label":       torch.tensor(label, dtype=torch.float),
        }

dataset  = RecDataset()
n        = len(dataset)
n_val    = max(1, int(n * 0.15))
n_train  = n - n_val
train_set, val_set = torch.utils.data.random_split(
    dataset, [n_train, n_val], generator=torch.Generator().manual_seed(42))
train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(val_set,   batch_size=BATCH_SIZE)

# ── 训练 ──────────────────────────────────────────────────
model     = GNNTransformerRec(num_users, num_items, EMBED_DIM).to(DEVICE)
optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-5)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
criterion = nn.BCEWithLogitsLoss()

print(f"参数量：{sum(p.numel() for p in model.parameters()):,}")
print(f"训练集={n_train}  验证集={n_val}\n开始训练...\n")

best_val  = float("inf")
log       = {"train_loss": [], "val_loss": []}

for epoch in range(1, EPOCHS + 1):
    model.train()
    total = 0.0
    for b in train_loader:
        optimizer.zero_grad()
        s = model(b["user_id"].to(DEVICE), b["item_id"].to(DEVICE),
                  b["seq"].to(DEVICE), b["u_neighbors"].to(DEVICE),
                  b["i_neighbors"].to(DEVICE), b["mask"].to(DEVICE))
        l = criterion(s, b["label"].to(DEVICE))
        l.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total += l.item() * len(b["label"])
    tl = total / n_train
    scheduler.step()

    model.eval()
    vl = 0.0
    with torch.no_grad():
        for b in val_loader:
            s  = model(b["user_id"].to(DEVICE), b["item_id"].to(DEVICE),
                       b["seq"].to(DEVICE), b["u_neighbors"].to(DEVICE),
                       b["i_neighbors"].to(DEVICE), b["mask"].to(DEVICE))
            vl += criterion(s, b["label"].to(DEVICE)).item() * len(b["label"])
    vl /= n_val

    log["train_loss"].append(round(tl, 5))
    log["val_loss"].append(round(vl, 5))

    if epoch % 10 == 0 or epoch == 1:
        print(f"Epoch {epoch:03d}/{EPOCHS} | TrainLoss={tl:.5f} | ValLoss={vl:.5f}", end="")
        if vl < best_val:
            best_val = vl
            torch.save(model.state_dict(), MODEL_SAVE)
            print("  [已保存]", end="")
        print()
    elif vl < best_val:
        best_val = vl
        torch.save(model.state_dict(), MODEL_SAVE)

LOG_SAVE.write_text(json.dumps(log, indent=2))
print(f"\n训练完成！最优 ValLoss={best_val:.5f}")
print(f"模型已保存：{MODEL_SAVE}")