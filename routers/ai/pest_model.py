"""
文件位置：backend/ai/pest_model.py
"""
import io, json, torch
import torch.nn as nn
from pathlib import Path
from torchvision import models, transforms
from PIL import Image

BASE_DIR     = Path(__file__).resolve().parent
MODEL_PATH   = BASE_DIR / "pest_model.pt"
CLASSES_PATH = BASE_DIR / "pest_classes.json"

TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

# ── 完整 38 类：英文 → (中文名, 防治建议, 描述) ─────────────────────
CLASS_MAP = {
    "Apple___Apple_scab": (
        "苹果轮纹病",
        "发病初期喷施三唑酮或苯醚甲环唑，7天一次连喷2-3次；雨前喷保护性杀菌剂，清除落叶减少侵染源。",
        "由苹果黑星病菌引起，叶片出现橄榄绿至黑褐色病斑，严重时导致早期落叶和果实畸形。"
    ),
    "Apple___Black_rot": (
        "苹果黑腐病",
        "剪除病枝并销毁，喷施波尔多液或代森锰锌；雨季前做好预防性喷药，及时摘除病果防止蔓延。",
        "由真菌引起，危害果实、叶片和枝条，果实出现棕褐色至黑色病斑并逐渐腐烂。"
    ),
    "Apple___Cedar_apple_rust": (
        "苹果锈病",
        "春季萌芽前喷石硫合剂，发病期喷三唑酮；彻底清除果园附近桧柏、龙柏等转主寄主植物。",
        "由锈菌引起的转主寄生病害，春季在苹果叶片上形成橙黄色病斑，严重影响光合作用。"
    ),
    "Apple___healthy": (
        "苹果（健康）",
        "植株状态良好，合理施肥灌溉，定期巡查监测，保持果园通风透光。",
        "叶片色泽正常，无病斑、虫孔，果树处于健康生长状态。"
    ),
    "Blueberry___healthy": (
        "蓝莓（健康）",
        "保持土壤酸性（pH 4.5-5.5），定期施有机肥，注意排水防涝，定期巡查。",
        "叶片深绿有光泽，植株生长旺盛，无病虫害症状。"
    ),
    "Cherry_(including_sour)___Powdery_mildew": (
        "樱桃白粉病",
        "喷施三唑酮或腈菌唑，7-10天一次；加强通风，避免密植，控制氮肥，增施钾肥提高抗性。",
        "叶片、嫩梢及果实表面覆盖白色粉状物，严重时叶片扭曲变形，影响产量和品质。"
    ),
    "Cherry_(including_sour)___healthy": (
        "樱桃（健康）",
        "注意防治蚜虫和桃蛀螟，保持果园排水畅通，避免过度灌溉。",
        "叶片正常，无病斑虫孔，树势旺盛，处于健康生长状态。"
    ),
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": (
        "玉米灰斑病",
        "发病初期喷施苯醚甲环唑或吡唑醚菌酯；合理密植保证通风，避免连作，选用抗病品种。",
        "叶片出现灰色至棕褐色长条形病斑，严重时叶片枯死，是玉米危害较重的叶部病害。"
    ),
    "Corn_(maize)___Common_rust_": (
        "玉米普通锈病",
        "发病初期喷施三唑酮或烯唑醇，7-10天一次；选种抗病品种，适期播种，避免氮肥过量。",
        "叶片两面散生大量铁锈色粉状孢子堆，严重时全株变褐，影响灌浆，导致减产。"
    ),
    "Corn_(maize)___Northern_Leaf_Blight": (
        "玉米大斑病",
        "喷施代森锰锌或苯醚甲环唑，发病初期效果最佳；清除田间病残体，选用抗病品种，合理密植。",
        "叶片上形成长梭形灰绿色至枯黄色大型病斑，严重时多个病斑连片导致整叶枯死。"
    ),
    "Corn_(maize)___healthy": (
        "玉米（健康）",
        "注意防治玉米螟，抽雄前可用辛硫磷颗粒剂点心，合理施肥保证营养充足。",
        "叶片嫩绿舒展，茎秆粗壮，无病斑虫孔，处于健康生长状态。"
    ),
    "Grape___Black_rot": (
        "葡萄黑腐病",
        "花前花后各喷一次甲基硫菌灵或嘧菌酯；及时清除病果病叶，减少初侵染源，雨后及时喷药保护。",
        "危害叶片、果实和枝蔓，果粒发病后迅速变黑皱缩，最终形成僵果悬挂枝上。"
    ),
    "Grape___Esca_(Black_Measles)": (
        "葡萄麻疹病",
        "目前无特效药，以预防为主：剪除病枝销毁，伤口涂抹愈合剂，保持园内通风，避免机械损伤。",
        "由多种木质部病原真菌复合侵染，叶片出现虎斑状失绿，果实产生黑色斑点，严重时植株慢性衰退。"
    ),
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": (
        "葡萄叶斑病",
        "喷施波尔多液或代森锰锌进行预防；雨季加强排水，避免叶片长期潮湿，及时摘除病叶。",
        "叶片上形成不规则褐色病斑，外围有黄色晕圈，严重时病叶早落，影响树势。"
    ),
    "Grape___healthy": (
        "葡萄（健康）",
        "注意霜霉病和灰霉病的预防，雨季前喷保护性杀菌剂，合理修剪保证通风透光。",
        "叶片浓绿有光泽，枝蔓健壮，无病斑虫孔，处于健康生长状态。"
    ),
    "Orange___Haunglongbing_(Citrus_greening)": (
        "柑橘黄龙病",
        "目前无有效治疗方法：严格防治柑橘木虱（喷施吡虫啉），发现病树立即挖除销毁，使用无病苗木建园。",
        "由韧皮部杆菌引起，通过柑橘木虱传播，症状为叶片黄化斑驳，果实小而畸形，是柑橘毁灭性病害。"
    ),
    "Peach___Bacterial_spot": (
        "桃细菌性穿孔病",
        "喷施农用链霉素或铜制剂，雨前雨后各喷一次；清除落叶，合理密植，加强通风排湿。",
        "叶片出现水渍状病斑后穿孔，果实出现疮痂状凹陷，严重影响商品价值。"
    ),
    "Peach___healthy": (
        "桃（健康）",
        "注意防治桃蚜和桃蛀螟，及时疏果，保证果实品质，加强夏季修剪改善通风条件。",
        "叶片正常，果实发育良好，无病斑虫孔，处于健康生长状态。"
    ),
    "Pepper,_bell___Bacterial_spot": (
        "甜椒细菌性疮痂病",
        "喷施铜制剂或农用链霉素，发病初期效果最佳；避免大水漫灌，及时摘除病叶病果，实行轮作。",
        "叶片产生水浸状小点后变为褐色病斑，果实出现疮痂状突起，严重降低商品性。"
    ),
    "Pepper,_bell___healthy": (
        "甜椒（健康）",
        "注意防治蚜虫和白粉虱，保持田间通风，适当控制水分，预防疫病发生。",
        "叶片深绿光亮，植株生长旺盛，无病斑虫孔，处于健康生长状态。"
    ),
    "Potato___Early_blight": (
        "马铃薯早疫病",
        "喷施代森锰锌或苯醚甲环唑，7-10天一次；合理密植，增施钾肥，避免过度灌溉，及时清除病叶。",
        "叶片出现同心轮纹状褐色病斑（靶斑），多从植株下部叶片开始发病，影响块茎产量。"
    ),
    "Potato___Late_blight": (
        "马铃薯晚疫病",
        "喷施烯酰吗啉或霜脲氰，发现中心病株立即处理；降低田间湿度，避免阴雨天浇水，选用抗病品种。",
        "由致病疫霉引起，叶片迅速出现大型水渍状褐色病斑，湿度大时叶背有白色霉层，可造成毁灭性损失。"
    ),
    "Potato___healthy": (
        "马铃薯（健康）",
        "注意防治马铃薯甲虫和蚜虫，合理施肥，保证排水畅通，防止块茎腐烂。",
        "叶片浓绿，茎秆直立，无病斑虫孔，处于健康生长状态。"
    ),
    "Raspberry___healthy": (
        "树莓（健康）",
        "注意定期修剪老枝，保持园内通风，防治蚜虫和红蜘蛛，适时浇水施肥。",
        "叶片正常，枝条健壮，无病斑虫孔，处于健康生长状态。"
    ),
    "Soybean___healthy": (
        "大豆（健康）",
        "注意防治大豆蚜虫和食心虫，合理轮作，避免连作，适时施用根瘤菌肥料。",
        "叶片翠绿，植株整齐，无病斑虫孔，根系发育良好，处于健康生长状态。"
    ),
    "Squash___Powdery_mildew": (
        "南瓜白粉病",
        "发病初期喷施三唑酮或硫磺悬浮剂；加强通风透光，避免密植，控制氮肥，增施磷钾肥提高抗性。",
        "叶片正反面覆盖白色粉状物，严重时整叶变黄枯死，高温干燥条件下发病尤为严重。"
    ),
    "Strawberry___Leaf_scorch": (
        "草莓叶焦病",
        "喷施代森锰锌或百菌清；避免过度灌溉，保持叶片干燥，及时摘除病叶，增施有机肥提高抗性。",
        "叶片出现小红紫色斑点并扩大，病斑中心变灰，边缘暗紫色，严重时叶片枯萎脱落。"
    ),
    "Strawberry___healthy": (
        "草莓（健康）",
        "注意防治灰霉病和蚜虫，保持适当温湿度，避免氮肥过多，保证果实甜度。",
        "叶片嫩绿光亮，植株匍匐茎健壮，无病斑虫孔，处于健康生长状态。"
    ),
    "Tomato___Bacterial_spot": (
        "番茄细菌性斑点病",
        "喷施铜制剂或农用链霉素，雨前雨后各喷一次；避免大水漫灌，及时清除病叶，种子消毒处理。",
        "叶片出现小水渍状斑点后变褐，果实出现疮痂状凸起，高温高湿多雨条件下发病严重。"
    ),
    "Tomato___Early_blight": (
        "番茄早疫病",
        "喷施代森锰锌或苯醚甲环唑，7天一次；清除下部老叶改善通风，避免过量氮肥，实行轮作。",
        "叶片出现同心轮纹状褐色病斑（靶斑），多从植株下部开始，茎部可形成深褐色凹陷斑。"
    ),
    "Tomato___Late_blight": (
        "番茄晚疫病",
        "发现中心病株立即施药，喷施烯酰吗啉；控制棚内湿度，避免雨天浇水，清除销毁病株。",
        "叶片出现水渍状大型病斑，湿度大时叶背有白色霉层，果实形成褐色硬斑，可短时间内造成毁灭性损失。"
    ),
    "Tomato___Leaf_Mold": (
        "番茄叶霉病",
        "喷施腐霉利或嘧霉胺；保持大棚通风，控制湿度在85%以下，避免叶片结露，及时摘除下部病叶。",
        "叶片背面出现灰绿色至紫褐色绒状霉层，正面对应部位褪绿变黄，是保护地番茄常见病害。"
    ),
    "Tomato___Septoria_leaf_spot": (
        "番茄斑枯病",
        "喷施代森锰锌或铜制剂；及时摘除病叶，避免从上方浇水，实行2年以上轮作。",
        "叶片出现圆形小斑，病斑中央灰白，边缘深褐，斑内有小黑点，严重时叶片枯黄脱落。"
    ),
    "Tomato___Spider_mites Two-spotted_spider_mite": (
        "番茄红蜘蛛",
        "喷施阿维菌素或哒螨灵，注意叶片背面均匀喷药；干旱时及时浇水，释放捕食螨生物防治。",
        "刺吸植株汁液，叶片正面出现灰白色小斑点，背面有细小蜘蛛网，高温干旱下繁殖极快。"
    ),
    "Tomato___Target_Spot": (
        "番茄靶斑病",
        "喷施苯醚甲环唑或嘧菌酯；加强通风，避免植株过密，控制浇水量，及时摘除下部老叶。",
        "叶片出现同心轮纹状大型病斑，形似靶心，茎和果实也可受害，湿度大时发病迅速。"
    ),
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": (
        "番茄黄化曲叶病毒病",
        "防治传毒媒介烟粉虱是关键：喷施吡虫啉，选用抗病品种，悬挂黄色粘虫板，设防虫网，发现病株立即拔除。",
        "通过烟粉虱传播，新叶黄化上卷变小，植株矮缩，严重时绝收，是番茄毁灭性病害。"
    ),
    "Tomato___Tomato_mosaic_virus": (
        "番茄花叶病毒病",
        "防控蚜虫传播，喷施矿物油；操作农事前洗手，不使用烟草制品，接触病株后立即消毒，拔除重病株。",
        "叶片出现深浅绿色相间的花叶症状，有时叶片变形皱缩，果实出现褪绿斑，通过接触和蚜虫传播。"
    ),
    "Tomato___healthy": (
        "番茄（健康）",
        "合理浇水施肥，定期整枝打杈，注意白粉虱和蚜虫的预防监测，保持植株通风透光。",
        "叶片深绿舒展，茎秆粗壮，果实发育正常，无病斑虫孔，处于健康生长状态。"
    ),
}

_model = None
_classes = None
_device = "cuda" if torch.cuda.is_available() else "cpu"


def build_model(num_classes):
    model = models.efficientnet_b0(weights='IMAGENET1K_V1')
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    return model


def preload():
    """后端启动时调用，提前加载模型避免首次请求延迟"""
    global _model, _classes
    if _model is not None:
        return
    if not CLASSES_PATH.exists() or not MODEL_PATH.exists():
        print("[PestModel] 模型文件不存在，跳过预加载")
        return
    _classes = json.loads(CLASSES_PATH.read_text(encoding="utf-8"))
    _model = build_model(len(_classes))
    _model.load_state_dict(torch.load(MODEL_PATH, map_location=_device))
    _model.to(_device).eval()
    # 预热推理，消除首次调用额外延迟
    with torch.no_grad():
        _model(torch.zeros(1, 3, 224, 224, device=_device))
    print(f"[PestModel] 预加载完成，设备={_device}，{len(_classes)} 类")


def predict(image_bytes: bytes) -> dict:
    global _model, _classes
    if _model is None:
        preload()
    if _model is None:
        raise FileNotFoundError("模型文件不存在，请先运行 train_pest.py")

    img    = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = TRANSFORM(img).unsqueeze(0).to(_device)
    with torch.no_grad():
        probs      = torch.softmax(_model(tensor), dim=1)[0]
        top_idx    = int(probs.argmax())
        confidence = float(probs[top_idx])

    en_name = _classes[top_idx]
    entry   = CLASS_MAP.get(en_name, (en_name, "建议咨询专业农技人员。", "暂无描述。"))
    zh_name, advice, description = entry

    level = "无" if "healthy" in en_name.lower() else \
            "严重" if confidence > 0.85 else \
            "中度" if confidence > 0.65 else "轻度"

    return {"predicted": zh_name, "confidence": round(confidence, 3),
            "level": level, "advice": advice, "description": description,
            "source": "efficientnet-b0"}