import json, platform
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if platform.system() == 'Windows':
    plt.rcParams['font.family'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
else:
    plt.rcParams['font.family'] = ['Noto Sans CJK SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def plot_pest():
    log_path = BASE_DIR / "pest_train_log.json"
    if not log_path.exists():
        print("病虫害训练日志不存在，跳过（请先运行 train_pest.py）")
        return

    log    = json.loads(log_path.read_text())
    epochs = list(range(1, len(log["train_loss"]) + 1))

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EfficientNet-B0 病虫害识别 - 训练过程", fontsize=14, fontweight="bold")

    axes[0].plot(epochs, log["train_loss"], "b-o", markersize=3, label="训练 Loss")
    axes[0].plot(epochs, log["val_loss"],   "r-o", markersize=3, label="验证 Loss")
    axes[0].set_title("Loss 曲线"); axes[0].set_xlabel("Epoch"); axes[0].set_ylabel("Loss")
    axes[0].legend(); axes[0].grid(True, alpha=0.3)

    best_acc = max(log["val_acc"])
    best_ep  = log["val_acc"].index(best_acc) + 1
    axes[1].plot(epochs, [v * 100 for v in log["val_acc"]], "g-o", markersize=3, label="验证准确率")
    axes[1].axvline(best_ep, color="orange", linestyle="--", alpha=0.7, label=f"最优 Epoch={best_ep}")
    axes[1].axhline(best_acc * 100, color="orange", linestyle=":", alpha=0.7)
    axes[1].set_title(f"验证准确率（最优：{best_acc*100:.1f}%）")
    axes[1].set_xlabel("Epoch"); axes[1].set_ylabel("准确率 (%)")
    axes[1].set_ylim(0, 105); axes[1].legend(); axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    save_path = BASE_DIR / "pest_training_curve.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] 病虫害训练曲线已保存：{save_path}")


def plot_rec():
    log_path = BASE_DIR / "rec_train_log.json"
    if not log_path.exists():
        print("推荐模型训练日志不存在，跳过（请先运行 train_rec.py）")
        return

    log    = json.loads(log_path.read_text())
    epochs = list(range(1, len(log["train_loss"]) + 1))

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.suptitle("GNN+Transformer 推荐模型 - 训练过程", fontsize=14, fontweight="bold")

    ax.plot(epochs, log["train_loss"], "b-",  linewidth=1.5, label="训练 Loss")
    ax.plot(epochs, log["val_loss"],   "r--", linewidth=1.5, label="验证 Loss")
    best_val = min(log["val_loss"])
    best_ep  = log["val_loss"].index(best_val) + 1
    ax.axvline(best_ep, color="orange", linestyle="--", alpha=0.7,
               label=f"最优 Epoch={best_ep} (Loss={best_val:.4f})")
    ax.set_title("BCE Loss 曲线"); ax.set_xlabel("Epoch"); ax.set_ylabel("Loss")
    ax.legend(); ax.grid(True, alpha=0.3)

    plt.tight_layout()
    save_path = BASE_DIR / "rec_training_curve.png"
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] 推荐模型训练曲线已保存：{save_path}")


if __name__ == "__main__":
    print("生成训练曲线图...\n")
    plot_pest()
    plot_rec()
    print("\n完成！图片在 backend/ai/ 目录下")