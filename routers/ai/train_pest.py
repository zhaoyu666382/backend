import json
import time
import torch
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader, random_split
from torchvision import datasets

from pest_model import build_model, TRANSFORM, BASE_DIR

DATA_DIR     = BASE_DIR / "data" / "plantvillage"
MODEL_SAVE   = BASE_DIR / "pest_model.pt"
CLASSES_SAVE = BASE_DIR / "pest_classes.json"
LOG_SAVE     = BASE_DIR / "pest_train_log.json"

BATCH_SIZE = 32
EPOCHS     = 25
LR         = 1e-4
VAL_RATIO  = 0.2
DEVICE     = "cuda" if torch.cuda.is_available() else "cpu"

if not DATA_DIR.exists():
    raise FileNotFoundError(
        f"\n数据集目录不存在：{DATA_DIR}\n"
        "请将 PlantVillage 数据集解压到 backend/ai/data/plantvillage/ 目录\n"
        "确保目录下有各病害子文件夹，如 Apple___Apple_scab/ 等"
    )

print(f"[配置] 设备={DEVICE}  批次={BATCH_SIZE}  轮数={EPOCHS}")

dataset = datasets.ImageFolder(str(DATA_DIR), transform=TRANSFORM)
classes = dataset.classes
json.dump(classes, open(CLASSES_SAVE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"发现 {len(classes)} 个类别，共 {len(dataset)} 张图片")

n       = len(dataset)
n_val   = int(n * VAL_RATIO)
n_train = n - n_val
train_set, val_set = random_split(dataset, [n_train, n_val],
                                   generator=torch.Generator().manual_seed(42))
train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True,  num_workers=0)
val_loader   = DataLoader(val_set,   batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
print(f"训练集：{n_train}  验证集：{n_val}\n")

model = build_model(len(classes)).to(DEVICE)

for name, param in model.named_parameters():
    if "features.8" in name or "classifier" in name:
        param.requires_grad = True
    else:
        param.requires_grad = False

optimizer = torch.optim.Adam(
    filter(lambda p: p.requires_grad, model.parameters()), lr=LR)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer, mode='max', factor=0.5, patience=3)
criterion = nn.CrossEntropyLoss()

best_acc = 0.0
log = {"train_loss": [], "val_acc": [], "val_loss": []}

for epoch in range(1, EPOCHS + 1):
    if epoch == 10:
        print("\n[第10轮] 解冻所有层，全局微调")
        for param in model.parameters():
            param.requires_grad = True
        for g in optimizer.param_groups:
            g['lr'] = LR * 0.1

    model.train()
    train_loss = 0.0
    t0 = time.time()
    for imgs, labels in train_loader:
        imgs, labels = imgs.to(DEVICE), labels.to(DEVICE)
        optimizer.zero_grad()
        loss = criterion(model(imgs), labels)
        loss.backward()
        optimizer.step()
        train_loss += loss.item() * len(imgs)
    train_loss /= n_train

    model.eval()
    val_loss = correct = 0
    with torch.no_grad():
        for imgs, labels in val_loader:
            imgs, labels = imgs.to(DEVICE), labels.to(DEVICE)
            logits = model(imgs)
            val_loss += criterion(logits, labels).item() * len(imgs)
            correct  += (logits.argmax(1) == labels).sum().item()
    val_loss /= n_val
    val_acc   = correct / n_val

    log["train_loss"].append(round(train_loss, 4))
    log["val_loss"].append(round(val_loss, 4))
    log["val_acc"].append(round(val_acc, 4))
    scheduler.step(val_acc)

    print(f"Epoch {epoch:02d}/{EPOCHS} | Loss={train_loss:.4f} | ValAcc={val_acc:.4f} | {time.time()-t0:.1f}s",
          end="")

    if val_acc > best_acc:
        best_acc = val_acc
        torch.save(model.state_dict(), MODEL_SAVE)
        print("  [已保存]", end="")
    print()

import json as _json
open(LOG_SAVE, 'w').write(_json.dumps(log, indent=2))
print(f"\n训练完成！最优准确率：{best_acc*100:.1f}%")
print(f"模型已保存：{MODEL_SAVE}")