"""Product-family taxonomy: FDA product code -> 产品族 (150-220 families).

Why a family layer?
-------------------
``config/product_code_tracks.json`` maps ~2k product codes onto 38 investment
tracks. A track answers "which theme is heating up"; it is too coarse to answer
"which *product* is heating up" - ``cardiac_rhythm`` lumps pacemakers, ICDs,
leads and EP catheters together. ``product_families.json`` adds the middle
layer: a curated, reproducible clustering of openFDA *generic device names* into
150-220 product families, each with a Chinese name, an English name, a category
and the exact keyword evidence that assigned each code.

Design rules
------------
* **Keyword evidence, not embeddings.** Every assignment is explainable: a code
  joins a family only because its generic name (or, failing that, its
  definition) contains one of the family's keywords. The longest matching
  keyword wins, so ``LEADLESS PACEMAKER`` beats the generic ``PACEMAKER`` rule.
* **Conflicts and unknowns stay visible.** A code matched by two families with
  equally specific keywords, or with no keyword and no usable specialty, is
  written to ``unclassified`` with a reason. It is never force-fitted into a
  family just to raise coverage.
* **Specialty fallback is honest.** Codes that match no named family but do
  carry a usable FDA medical specialty go to an explicit ``其他…`` family whose
  note says "仅按专科归档，低置信度". These families are a safety net, not a
  substitute for real product families.
* **Deterministic.** No timestamps, no dict iteration order leaks: the same
  database always produces the same JSON byte-for-byte.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from .config import CONFIG_DIR
from .util import norm_text, read_json, write_json

FAMILIES_FILE = CONFIG_DIR / "product_families.json"
UNCLASSIFIED = "unclassified"
BUILD_ID = "product_families_v1"

MIN_FAMILIES = 150
MAX_FAMILIES = 220

# Category display order in the generated JSON (not alphabetical: clinical logic).
CATEGORY_ORDER = [
    "心血管",
    "结构性心脏病",
    "外周与神经血管",
    "影像与放疗",
    "骨科",
    "神经调控与神经外科",
    "体外诊断",
    "外科与内镜",
    "眼科",
    "口腔",
    "耳鼻喉",
    "泌尿",
    "女性健康",
    "呼吸与麻醉",
    "患者监护",
    "输注与糖尿病",
    "肾脏与透析",
    "伤口与止血",
    "康复与辅助",
    "医美与整形",
    "感染控制与医院耗材",
    "数字医疗",
    "其他",
]


def _f(
    family_id: str,
    name_zh: str,
    name_en: str,
    category: str,
    keywords: Iterable[str],
    note: str,
) -> dict[str, Any]:
    return {
        "id": family_id,
        "name_zh": name_zh,
        "name_en": name_en,
        "category": category,
        "keywords": [k for k in keywords if k],
        "note": note,
    }


# ---------------------------------------------------------------------------
# Curated family dictionary. Keywords are matched against the normalised
# generic device name first, then against the normalised definition. Longer
# keyword wins. Keep the vocabulary in the order used by openFDA generic names
# (``Head, qualifier, qualifier``) - see https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD/classification.cfm
# ---------------------------------------------------------------------------
FAMILY_SPECS: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- 心血管
    _f("cvd_rhythm_implant", "心脏节律植入装置（起搏器/ICD/CRT/导线）", "Cardiac Rhythm Implantable Devices", "心血管",
       ["Implantable Cardioverter Defibrillator", "Defibrillator, Automatic Implantable", "Implantable Defibrillator",
        "Cardiac Resynchronization", "Pacemaker", "Pulse Generator", "Pulse-Generator", "Defibrillator Electrode",
        "Pacemaker Electrode", "Pacemaker Electrodes", "Leadless Pacemaker", "Permanent Defibrillator Electrodes",
        "Implantable Pulse Generator", "Permanent, Implantable", "Cardiac Rhythm"],
       "起搏器、ICD/CRT-D、CRT-P、起搏/除颤导线与无导线起搏器；公司 CRM 产品线的聚合层。"),
    _f("cvd_ep_ablation", "电生理消融导管与消融系统", "Cardiac Ablation Catheters and Generators", "心血管",
       ["Cardiac Ablation", "Ablation Catheter", "Pulsed Field Ablation", "Irreversible Electroporation",
        "Cryoablation", "Ablation, Cardiac", "Electrophysiology Catheter", "Ablation Generator"],
       "房颤/房扑射频、冷冻与脉冲场消融（PFA）导管及消融发生器。"),
    _f("cvd_ep_mapping", "电生理标测系统与标测导管", "Electrophysiology Mapping Systems", "心血管",
       ["Electrophysiology", "Mapping System", "Electroanatomic", "Mapping Catheter", "Catheter, Electrode Recording",
        "Electrode Recording, Or Probe", "3D Mapping", "Cardiac Mapping", "Navigation, Cardiac"],
       "三维电解剖标测、标测/记录电极导管，消融术前诊断与术中导航。"),
    _f("cvd_ecg", "心电诊断与动态心电监护", "ECG Diagnostic and Holter Monitors", "心血管",
       ["Electrocardiograph", "Electrocardiogram", "Holter", "Event Monitor", "ECG", "Stress Test System",
        "Treadmill", "Vectorcardiograph"],
       "静息/动态心电图机、Holter、运动负荷试验与心电事件记录仪。"),
    _f("cvd_implant_monitor", "植入式心电监测（ILR）", "Implantable Cardiac Monitors", "心血管",
       ["Implantable Cardiac Monitor", "Insertable Cardiac Monitor", "Loop Recorder", "Implantable Loop",
        "Cardiac Monitor, Implantable"],
       "植入式循环记录仪/皮下心电监测，用于不明原因晕厥与房颤筛查。"),
    _f("cvd_remote", "心脏远程监测与可穿戴心电", "Cardiac Remote Monitoring and Wearables", "心血管",
       ["Remote Monitoring", "Telemetry", "Wearable Cardiac", "Mobile Cardiac", "Cardiac Telemetry",
        "Remote Cardiac"],
       "院外遥测、可穿戴心电贴与远程随访平台。"),
    # ------------------------------------------------------------ 结构性心脏病
    _f("sh_tavr", "经导管主动脉瓣置换（TAVR）", "Transcatheter Aortic Valves", "结构性心脏病",
       ["Aortic Valve, Prosthesis, Percutaneously Delivered", "Transcatheter Aortic", "TAVR", "TAVI",
        "Percutaneously Delivered Aortic"],
       "经股/经心尖主动脉瓣置换瓣膜与输送系统。"),
    _f("sh_valve_surgical", "外科心脏瓣膜与瓣环", "Surgical Heart Valves and Annuloplasty", "结构性心脏病",
       ["Heart-Valve", "Heart Valve, Non-Allograft", "Valve, Heart", "Annuloplasty Ring", "Heart Valve Prosthesis"],
       "机械瓣、生物瓣等外科置换瓣膜及瓣环成形环。"),
    _f("sh_mitral", "二尖瓣/三尖瓣修复与置换", "Mitral and Tricuspid Repair/Replacement", "结构性心脏病",
       ["Mitral Valve", "Tricuspid", "Mitral Annuloplasty", "Mitral Clip", "Mitral Repair"],
       "经导管二尖瓣/三尖瓣夹合、修复与置换器械。"),
    _f("sh_occluder", "结构性心脏封堵器", "Structural Heart Occluders", "结构性心脏病",
       ["Occluder", "Septal Occluder", "Appendage Closure", "Left Atrial Appendage", "Patent Ductus",
        "Patent Foramen", "Atrial Septal Defect", "Ventricular Septal Defect", "PFO"],
       "PFO/ASD/VSD 封堵器、左心耳封堵器、动脉导管未闭封堵器。"),
    _f("sh_hf_mcs", "心衰与机械循环支持（VAD/IABP/ECMO）", "Heart Failure and Mechanical Circulatory Support", "结构性心脏病",
       ["Ventricular (Assist) Bypass", "Ventricular Assist", "Artificial Heart", "Blood Pump", "Intra-Aortic",
        "Heart Support", "Extracorporeal Membrane", "ECMO", "Cardiac Assist"],
       "左心室辅助装置、人工心脏、主动脉内球囊反搏与 ECMO 循环支持。"),
    _f("sh_cardiac_surgery", "体外循环与心脏外科耗材", "Cardiopulmonary Bypass and Cardiac Surgery", "结构性心脏病",
       ["Oxygenator", "Cardiopulmonary Bypass", "Perfusion", "Cannula And Tubing, Vascular, Cardiopulmonary",
        "Cardiotomy", "Heart-Lung", "Cardiac Surgery"],
       "体外循环氧合器、滚压/离心泵、心肌切开吸引与心脏外科插管。"),
    # -------------------------------------------------------- 外周与神经血管
    _f("vasc_coronary_stent", "冠脉支架", "Coronary Stents", "外周与神经血管",
       ["Coronary Drug-Eluting Stent", "Coronary Stent", "Stent, Coronary", "Drug-Eluting Coronary",
        "Bare Metal Coronary"],
       "药物洗脱与裸金属冠脉支架。"),
    _f("vasc_coronary_balloon", "冠脉球囊与旋磨旋切", "Coronary Balloons and Atherectomy", "外周与神经血管",
       ["Percutaneous Transluminal Coronary Angioplasty", "PTCA", "Coronary Angioplasty", "Cutting/Scoring",
        "Coronary Atherectomy", "Atherectomy", "Coronary Balloon"],
       "PTCA 球囊、切割/刻痕球囊、冠脉旋磨与斑块旋切系统。"),
    _f("vasc_guidewire", "导丝与导引导管", "Guidewires and Guiding Catheters", "外周与神经血管",
       ["Guide, Catheter", "Guide Wire", "Guidewire", "Guiding Catheter", "Guide Catheter"],
       "介入导丝、导引导管与微导管导向器械。"),
    _f("vasc_peripheral_stent", "外周动脉支架", "Peripheral Arterial Stents", "外周与神经血管",
       ["Stent, Superficial Femoral Artery", "Stent, Iliac", "Stent, Renal", "Peripheral Stent",
        "Iliac Covered Stent", "Femoropopliteal", "Stent, Peripheral", "Stent, Biliary"],
       "股浅/髂/肾动脉等外周支架，含覆膜支架与胆道支架。"),
    _f("vasc_peripheral_balloon", "外周球囊与药物球囊", "Peripheral and Drug-Coated Balloons", "外周与神经血管",
       ["Drug-Eluting Peripheral", "Peripheral Transluminal Angioplasty", "Angioplasty, Peripheral",
        "Peripheral Balloon", "Percutaneous Transluminal Angioplasty Catheter"],
       "外周普通球囊、药物涂层球囊与 PTA 导管。"),
    _f("vasc_thrombectomy", "血栓清除与取栓", "Thrombectomy and Embolectomy", "外周与神经血管",
       ["Thrombectomy", "Embolectomy", "Thrombus Retriever", "Clot Retrieval", "Aspiration Catheter"],
       "外周动静脉血栓抽吸、机械取栓与栓子清除导管。"),
    _f("vasc_closure", "血管闭合与止血装置", "Vascular Closure and Hemostasis", "外周与神经血管",
       ["Hemostasis, Vascular", "Vascular Closure", "Closure Device, Vascular", "Arteriotomy",
        "Puncture Closure", "Compression Device"],
       "穿刺点闭合器、压迫止血装置与血管封堵。"),
    _f("vasc_access", "血管穿刺与通路器械", "Vascular Access Devices", "外周与神经血管",
       ["Introducer", "Sheath, Introducer", "Vascular Access", "Catheter, Intravascular, Diagnostic",
        "Catheter, Intravascular, Therapeutic"],
       "血管鞘、扩张器、诊断/治疗性血管内导管等介入入路器械。"),
    _f("vasc_graft", "人工血管与主动脉腔内移植物", "Vascular Grafts and Endografts", "外周与神经血管",
       ["Vascular Graft", "Endovascular Graft", "Stent Graft", "Aortic Aneurysm", "Prosthesis, Vascular"],
       "开放手术人工血管、主动脉瘤腔内修复（EVAR/TEVAR）覆膜支架。"),
    _f("vasc_ivc", "腔静脉滤器与静脉介入", "Vena Cava Filters and Venous Intervention", "外周与神经血管",
       ["Vena Cava Filter", "IVC Filter", "Venous Stent", "Venous"],
       "下腔静脉滤器、静脉支架与静脉曲张消融导管。"),
    _f("vasc_diagnostic", "血管内影像与功能学评估（IVUS/OCT/FFR）", "Intravascular Imaging and Physiology", "外周与神经血管",
       ["Intravascular Ultrasound", "Optical Coherence Tomography", "Fractional Flow", "FFR",
        "Intravascular Imaging"],
       "血管内超声、光学相干断层成像与血流储备分数评估。"),
    _f("nv_aneurysm", "颅内动脉瘤治疗装置", "Intracranial Aneurysm Devices", "外周与神经血管",
       ["Intracranial Aneurysm", "Flow Diverter", "Aneurysm Coil", "Embolization Coil", "Aneurysm Clip"],
       "弹簧圈、血流导向装置、动脉瘤夹与瘤内栓塞器械。"),
    _f("nv_stent", "颈动脉与颅内支架", "Carotid and Intracranial Stents", "外周与神经血管",
       ["Stent, Carotid", "Carotid Stent", "Intracranial Stent", "Neurovascular Stent"],
       "颈动脉支架、颅内动脉狭窄支架与神经血管支架。"),
    _f("nv_thrombectomy", "神经介入取栓", "Neurothrombectomy Devices", "外周与神经血管",
       ["Neurothrombectomy", "Stent Retriever", "Thrombus Retriever, Neurovascular",
        "Mechanical Thrombectomy, Neuro"],
       "急性缺血性卒中支架取栓器与神经血管抽吸导管。"),
    _f("nv_catheter", "神经介入导管与微导管", "Neurovascular Catheters", "外周与神经血管",
       ["Neurovasculature", "Neurovascular Catheter", "Microcatheter", "Catheter, Percutaneous, Neurovasculature"],
       "神经介入微导管、球囊与通路导管。"),
    _f("nv_embolic", "栓塞材料与液体栓塞剂", "Embolic Materials", "外周与神经血管",
       ["Embolic", "Embolization", "Liquid Embolic", "Onyx", "Embolotherapy", "Promoting Embolization"],
       "PVA 颗粒、弹簧圈栓塞材料、Onyx 等液体栓塞剂与栓塞微球。"),
    # ------------------------------------------------------------ 影像与放疗
    _f("img_mri", "磁共振成像系统与线圈", "MRI Systems and Coils", "影像与放疗",
       ["Nuclear Magnetic Resonance", "Magnetic Resonance Imaging", "Coil, Magnetic Resonance", "MR System",
        "MRI System"],
       "MRI 主机、射频线圈与磁共振波谱设备。"),
    _f("img_ct", "计算机断层扫描（CT）", "Computed Tomography Systems", "影像与放疗",
       ["Tomography, Computed", "Computed Tomography", "CT Scanner", "X-Ray, Tomography, Computed"],
       "CT 扫描机、能谱 CT 与锥形束 CT。"),
    _f("img_xray", "X射线摄影与透视系统", "X-Ray Radiography and Fluoroscopy", "影像与放疗",
       ["X-Ray", "Radiographic", "Fluoroscopic", "Angiographic", "Solid State X-Ray Imager", "C-Arm",
        "Mobile X-Ray"],
       "DR/CR 摄影、C 型臂、移动 X 射线机与平板探测器。"),
    _f("img_interventional", "介入透视与导管室影像", "Interventional Fluoroscopy Systems", "影像与放疗",
       ["Interventional Fluoroscopic", "Angiographic X-Ray", "Cath Lab", "Interventional X-Ray"],
       "导管室/杂交手术室用介入透视影像系统。"),
    _f("img_us", "超声成像系统与探头", "Ultrasound Systems and Transducers", "影像与放疗",
       ["Ultrasonic", "Ultrasound", "Echocardiograph", "Doppler", "Transducer, Ultrasonic", "Sonograph"],
       "彩色多普勒、便携/床旁超声、腔内探头与超声换能器。"),
    _f("img_nuclear", "核医学与PET", "Nuclear Medicine and PET", "影像与放疗",
       ["Emission Tomography", "Nuclear Medicine", "Gamma Camera", "PET Scanner", "Radionuclide Imaging"],
       "SPECT/PET 扫描仪、伽马相机与核医学影像设备。"),
    _f("img_ai", "影像后处理软件与影像AI", "Radiological Image Processing and AI", "影像与放疗",
       ["Image Processing, Radiological", "Automated Radiological", "Radiological Computer",
        "Computer-Assisted", "Image Analysis", "Radiological Image"],
       "放射影像工作站的图像后处理、CAD 与 AI 辅助诊断软件。"),
    _f("img_display", "影像显示、归档与打印", "Imaging Display, PACS and Printing", "影像与放疗",
       ["Display, Diagnostic Radiology", "Image Management", "Picture Archiving", "PACS", "Dry Imager",
        "Medical Image Printer"],
       "诊断显示器、PACS/影像管理软件与医用胶片打印机。"),
    _f("img_rt", "放射治疗设备与治疗计划", "Radiation Therapy Equipment and Planning", "影像与放疗",
       ["Radiation Therapy", "Linear Accelerator", "Charged-Particle", "Brachytherapy",
        "Radionuclide Applicator", "Treatment Planning", "Radiotherapy"],
       "直线加速器、质子/重离子、近距离放疗与放疗计划系统。"),
    _f("img_mammo", "乳腺影像", "Breast Imaging", "影像与放疗",
       ["Mammograph", "Breast Imaging", "Breast Tomosynthesis"],
       "乳腺 X 线摄影、数字乳腺断层与乳腺超声。"),
    _f("img_dental", "口腔影像设备", "Dental Imaging", "影像与放疗",
       ["Dental X-Ray", "Dental Tomography", "Extraoral Source", "Intraoral"],
       "口内牙片机、口腔 CBCT 与全景机。"),
    # ------------------------------------------------------------------ 骨科
    _f("orth_spine_fusion", "脊柱融合与椎间植入物", "Spinal Fusion and Interbody Devices", "骨科",
       ["Intervertebral Fusion", "Interbody Fusion", "Spinal Fusion", "Corpectomy",
        "Vertebral Body Replacement", "Intervertebral Fusion Device"],
       "椎间融合器、cage、椎体替代与植骨融合系统。"),
    _f("orth_spine_fixation", "脊柱内固定", "Spinal Fixation Systems", "骨科",
       ["Pedicle Screw", "Thoracolumbosacral", "Spinal Fixation", "Spinal System", "Posterior Cervical Screw",
        "Facet Screw", "Spinous Process", "Laminoplasty", "Occipitocervical", "Thoracolumbar"],
       "椎弓根钉棒、颈椎前路/后路钢板、侧块螺钉等脊柱内固定。"),
    _f("orth_spine_other", "脊柱其他（椎间盘/椎体成形）", "Other Spinal Devices", "骨科",
       ["Intervertebral Disc", "Vertebroplasty", "Kyphoplasty", "Spinal Implant", "Disc Nucleus", "Interspinous"],
       "人工椎间盘、椎体成形/后凸成形与棘突间撑开器。"),
    _f("orth_trauma_plate", "骨科钢板与接骨板", "Orthopedic Plates", "骨科",
       ["Plate, Fixation, Bone", "Bone Plate", "Fracture Plate", "Tibial Plateau", "Plating System"],
       "四肢/骨盆骨折锁定钢板、接骨板与微型钢板。"),
    _f("orth_trauma_screw", "骨钉、骨螺钉与髓内钉", "Bone Screws and Intramedullary Nails", "骨科",
       ["Intramedullary", "Screw, Fixation, Bone", "Bone Screw", "Staple, Fixation, Bone",
        "Nail/Blade/Plate", "Dynamic Hip Screw", "Interlocking Nail"],
       "髓内钉、空心钉、骨螺钉、骨钉与骨固定夹。"),
    _f("orth_joint_hip", "髋关节假体", "Hip Prostheses", "骨科",
       ["Prosthesis, Hip", "Hip Prosthesis", "Hemi-, Femoral", "Acetabular"],
       "全髋/半髋假体、髋臼杯与髋关节翻修系统。"),
    _f("orth_joint_knee", "膝关节假体", "Knee Prostheses", "骨科",
       ["Prosthesis, Knee", "Knee Prosthesis", "Patellofemorotibial", "Unicompartmental"],
       "全膝/单髁膝关节假体与髌股关节假体。"),
    _f("orth_joint_shoulder", "肩/肘/腕关节假体", "Shoulder, Elbow and Wrist Prostheses", "骨科",
       ["Prosthesis, Shoulder", "Prosthesis, Elbow", "Prosthesis, Wrist", "Shoulder Prosthesis",
        "Reverse Shoulder"],
       "反肩/解剖肩、肘与腕关节假体。"),
    _f("orth_joint_other", "踝与手足小关节假体", "Ankle and Small Joint Prostheses", "骨科",
       ["Prosthesis, Ankle", "Prosthesis, Toe", "Prosthesis, Finger", "Ankle Prosthesis", "Total Ankle"],
       "全踝、足趾与手指关节假体。"),
    _f("orth_biologics", "骨修复与骨移植材料", "Bone Graft and Bone Repair Materials", "骨科",
       ["Bone Void", "Bone Graft", "Demineralized", "Calcium Phosphate", "Bone Cement", "Osteoconductive",
        "Bone Filler", "Graft Substitute"],
       "骨水泥、人工骨、脱钙骨基质与骨形态发生蛋白载体。"),
    _f("orth_cmf", "颅颌面与颌面固定系统", "Craniomaxillofacial Fixation", "骨科",
       ["Craniomaxillofacial", "Maxillofacial", "Mandibular", "Cranial Fixation", "CMF", "Orbital"],
       "颌面接骨板、颅骨固定与正颌手术固定系统。"),
    _f("orth_softtissue", "运动医学与软组织固定", "Sports Medicine and Soft Tissue Fixation", "骨科",
       ["Fastener, Fixation, Soft Tissue", "Soft Tissue", "Suture Anchor", "Ligament", "Tendon", "Meniscus"],
       "带线锚钉、界面螺钉、韧带/半月板修复与软组织固定。"),
    _f("orth_external_fixation", "外固定与骨牵引", "External Fixation and Traction", "骨科",
       ["External Fixator", "Fixation, External", "Bone Transport", "Traction"],
       "外固定支架、环形外固定与骨搬运装置。"),
    _f("orth_instrument", "骨科手术器械与导航", "Orthopedic Instruments and Navigation", "骨科",
       ["Orthopedic Stereotaxic", "Orthopedic Tray", "Bone Drill", "Surgical Navigation",
        "Orthopedic Instrument", "Bone Saw", "Orthopedic Implant Trial"],
       "骨科动力工具、试模、器械包与手术导航。"),
    # ------------------------------------------------- 神经调控与神经外科
    _f("neuro_scs", "脊髓电刺激（SCS）", "Spinal Cord Stimulation", "神经调控与神经外科",
       ["Spinal-Cord", "Spinal Cord Stimulator", "Spinal Cord Stimulation"],
       "脊髓电刺激电极、IPG 与程控系统（慢性疼痛）。"),
    _f("neuro_dbs", "脑深部电刺激（DBS）", "Deep Brain Stimulation", "神经调控与神经外科",
       ["Parkinsonian", "Deep Brain", "DBS", "Brain Stimulator"],
       "脑深部刺激电极与脉冲发生器（帕金森/特发性震颤）。"),
    _f("neuro_pns", "周围神经与背根神经节刺激", "Peripheral and DRG Neuromodulation", "神经调控与神经外科",
       ["Dorsal Root Ganglion", "Peripheral Nerve Stimulator", "Peripheral Nerve Stimulation",
        "Occipital Nerve"],
       "背根神经节（DRG）与周围神经刺激系统。"),
    _f("neuro_vns", "迷走神经与自主神经刺激", "Vagus and Autonomic Nerve Stimulation", "神经调控与神经外科",
       ["Vagus", "Autonomic Nerve", "Epilepsy Stimulator", "Implanted Brain Stimulator For Epilepsy"],
       "迷走神经刺激（VNS）、自主神经刺激与癫痫脑刺激。"),
    _f("neuro_tens", "经皮神经电刺激（TENS）", "Transcutaneous Electrical Nerve Stimulation", "神经调控与神经外科",
       ["Transcutaneous", "TENS Unit", "Transcutaneous Electrical"],
       "TENS 理疗仪、经皮电刺激止痛与 OTC 电刺激设备。"),
    _f("neuro_muscle", "肌肉电刺激与神经肌肉康复", "Muscle Stimulation and NMES", "神经调控与神经外科",
       ["Stimulator, Muscle", "Neuromuscular", "Muscle Stimulator", "Muscle Conditioning"],
       "NMES 肌肉电刺激、盆底/吞咽/排痰等神经肌肉训练设备。"),
    _f("neuro_bone", "骨生长电刺激", "Bone Growth Stimulation", "神经调控与神经外科",
       ["Bone Growth"],
       "骨愈合电/磁刺激与骨生长促进装置。"),
    _f("neuro_sacral", "骶神经与胫神经调节", "Sacral and Tibial Neuromodulation", "神经调控与神经外科",
       ["Sacral Neuromodulation", "Sacral Nerve", "Tibial Nerve", "Sacral"],
       "骶神经调节（排尿/排便障碍）与胫神经刺激。"),
    _f("neuro_hypoglossal", "舌下神经刺激（睡眠呼吸暂停）", "Hypoglossal Nerve Stimulation", "神经调控与神经外科",
       ["Hypoglossal", "Upper Airway Stimulation"],
       "植入式舌下神经刺激治疗阻塞性睡眠呼吸暂停。"),
    _f("neuro_surgery", "神经外科器械与植入物", "Neurosurgical Devices", "神经调控与神经外科",
       ["Stereotaxic", "Neurosurgical", "Craniotomy", "Dura", "Neurological Tray", "Skull",
        "Cranial", "Brain Retractor", "Neuro Endoscope"],
       "立体定向头架、开颅器械、硬脑膜替代物与神经外科导航。"),
    _f("neuro_csf", "脑脊液分流与引流", "CSF Shunts and Drains", "神经调控与神经外科",
       ["Cerebrospinal", "Shunt, Central Nervous", "CSF", "Hydrocephalus", "External Ventricular Drain"],
       "脑室-腹腔分流、腰大池引流与颅内压监测。"),
    # --------------------------------------------------------------- 体外诊断
    _f("ivd_molecular", "分子诊断与基因测序", "Molecular Diagnostics and Sequencing", "体外诊断",
       ["Nucleic Acid", "Next Generation Sequencing", "PCR", "DNA Detection", "RNA Detection",
        "Somatic Gene Mutation", "Hybridization", "Gene Mutation", "Sequencing"],
       "PCR、NGS、核酸杂交与病原体/肿瘤基因检测。"),
    _f("ivd_immuno", "免疫分析与抗原抗体检测", "Immunoassays", "体外诊断",
       ["Immunoassay", "Enzyme Linked Immunosorbent", "Chemiluminescent", "Radioallergosorbent",
        "Immunologic", "Immuno", "Antibody Test", "Serology"],
       "ELISA、化学发光、免疫层析与过敏原/自身抗体检测。"),
    _f("ivd_chem", "临床生化分析", "Clinical Chemistry", "体外诊断",
       ["Clinical Chemistry", "Chemistry Analyzer", "Photometric", "Spectrophotometer", "Electrolyte Analyzer",
        "Chemistry Analyzer"],
       "生化分析仪、电解质与光度法/比浊法检测试剂。"),
    _f("ivd_micro", "微生物培养与药敏", "Microbiology and Susceptibility", "体外诊断",
       ["Culture", "Microbial", "Antimicrobial Susceptibility", "Susceptibility", "Blood Culture", "Gram Stain",
        "Microbiology"],
       "血培养、微生物鉴定、药敏试验与培养基。"),
    _f("ivd_hema", "血液学分析", "Hematology", "体外诊断",
       ["Hematology", "Blood Cell Count", "Coagulation", "Differential Cell", "Hemoglobin",
        "Hemostasis Analyzer", "Platelet"],
       "血细胞分析、凝血功能与血红蛋白检测。"),
    _f("ivd_pathology", "病理与免疫组化", "Pathology and IHC", "体外诊断",
       ["Immunohistochemistry", "Pathology", "Histology", "Cytology", "HER-2"],
       "免疫组化、组织病理与细胞学诊断试剂/设备。"),
    _f("ivd_tox", "毒理与治疗药物监测", "Toxicology and TDM", "体外诊断",
       ["Toxicology", "Drug Of Abuse", "Therapeutic Drug", "Drug Test"],
       "药物滥用筛查、治疗药物浓度监测与毒理学检测。"),
    _f("ivd_bloodbank", "血库与输血医学", "Blood Bank and Transfusion", "体外诊断",
       ["Blood Group", "Blood Bank", "Transfusion", "Serum Separator", "Blood Collection", "Crossmatch"],
       "血型鉴定、交叉配血、采血与输血耗材。"),
    _f("ivd_poct", "即时检验与自测", "Point-of-Care and Self-Testing", "体外诊断",
       ["Point Of Care", "Over The Counter", "Rapid Test", "Self-Test", "Home Test"],
       "POCT 快速检测、居家自测与 OTC 诊断产品。"),
    _f("ivd_genetics", "遗传与产前诊断", "Genetic and Prenatal Testing", "体外诊断",
       ["Genetic", "Prenatal", "Neural Tube Defect", "Karyotype", "Newborn Screening", "Cytogenetic"],
       "遗传病检测、产前筛查/诊断与新生儿筛查。"),
    _f("ivd_instrument", "检验自动化仪器", "Laboratory Automation", "体外诊断",
       ["Analyzer", "Automated Test", "Laboratory Instrument", "Sample Processing"],
       "流水线、样本前处理与实验室自动化设备。"),
    _f("ivd_reagent", "体外诊断试剂与校准品", "IVD Reagents and Calibrators", "体外诊断",
       ["Reagent", "Calibrator", "Control Material", "Assay", "Test Kit"],
       "通用试剂、校准品、质控品与检测试剂盒。"),
    # ------------------------------------------------------------- 外科与内镜
    _f("surg_energy", "电外科与能量平台", "Electrosurgery and Energy Platforms", "外科与内镜",
       ["Electrosurgical", "Cutting & Coagulation", "Argon Beam", "Vessel Sealing", "Energy Generator"],
       "高频电刀、氩气刀、血管闭合与能量发生器。"),
    _f("surg_laser", "激光手术设备", "Surgical Lasers", "外科与内镜",
       ["Powered Laser Surgical", "Laser, Surgical", "Surgical Laser", "Laser System", "Excimer Laser",
        "Femtosecond"],
       "外科/泌尿/口腔激光治疗机与光纤。"),
    _f("surg_ablation", "肿瘤消融与热消融设备", "Tumor Ablation Systems", "外科与内镜",
       ["Thermal Ablation", "Microwave Ablation", "Cryosurgical", "Radiofrequency Ablation",
        "Ablation System", "Irreversible Electroporation Ablation"],
       "射频/微波/冷冻消融与不可逆电穿孔肿瘤治疗设备。"),
    _f("surg_robot", "手术机器人与计算机辅助手术", "Surgical Robotics and Navigation", "外科与内镜",
       ["Surgical, Computer Controlled", "Robotic Surgery", "Surgical Robot", "Computer Controlled Instrument",
        "Surgical Navigation"],
       "腔镜手术机器人、计算机辅助手术与术中导航。"),
    _f("surg_laparoscopy", "腹腔镜与硬性内镜", "Laparoscopes and Rigid Endoscopes", "外科与内镜",
       ["Laparoscope", "Laparoscopic", "Arthroscope", "Thoracoscope", "Mediastinoscope", "Cystoscope",
        "Hysteroscope", "Resectoscope"],
       "腹腔镜、关节镜、胸腔镜、宫腔镜等硬镜及配套器械。"),
    _f("surg_endoscope", "软性内窥镜", "Flexible Endoscopes", "外科与内镜",
       ["Endoscope", "Colonoscope", "Gastroscope", "Bronchoscope", "Sigmoidoscope", "Duodenoscope",
        "Choledochoscope", "Nasopharyngoscope", "Esophagoscope"],
       "胃肠镜、支气管镜、十二指肠镜等软镜与附件。"),
    _f("surg_stapler", "吻合器与切割闭合器", "Surgical Staplers", "外科与内镜",
       ["Stapler", "Surgical Stapler", "Circular Stapler", "Staple, Implantable", "Staple Line"],
       "管型/直线切割吻合器、吻合钉与闭合器械。"),
    _f("surg_instrument", "开放手术基础器械", "General Surgical Instruments", "外科与内镜",
       ["Scissor", "Forceps", "Retractor", "Clamp", "Scalpel", "Knife", "Dissector", "Curette",
        "Surgical Instrument", "Needle Holder"],
       "剪、钳、拉钩、刀、剥离器等基础开放手术器械。"),
    _f("surg_tray", "手术器械包与托盘", "Surgical Trays and Procedure Kits", "外科与内镜",
       ["Tray", "Kit, Surgical", "Procedure Kit", "Surgical Pack", "Custom Procedure", "General Surgery Tray",
        "Cardiovascular Procedure Kit"],
       "一次性手术包、器械托盘与科室定制手术套包。"),
    _f("surg_drape", "手术铺单与手术衣", "Surgical Drapes and Gowns", "外科与内镜",
       ["Drape", "Surgical Gown", "Gown, Surgical", "Surgical Cap", "Patient Drape"],
       "无菌手术铺单、手术衣与手术帽。"),
    _f("surg_suction", "吸引、冲洗与排烟", "Suction, Irrigation and Smoke Evacuation", "外科与内镜",
       ["Suction", "Irrigation", "Smoke Evacuation"],
       "术中吸引器、冲洗泵与电外科排烟系统。"),
    _f("surg_biopsy", "活检与穿刺器械", "Biopsy and Aspiration Devices", "外科与内镜",
       ["Biopsy", "Core Needle", "Aspiration Needle", "Biopsy Instrument", "Biopsy Gun"],
       "活检枪、穿刺针与真空辅助活检系统。"),
    _f("surg_power", "动力手术器械（钻/锯/铣）", "Powered Surgical Instruments", "外科与内镜",
       ["Powered Surgical Instrument", "Bone Saw", "Surgical Drill", "Cranial Perforator",
        "Oscillating Saw", "Pneumatic Driver"],
       "医用钻、锯、铣与气动/电动动力系统。"),
    _f("surg_light", "手术照明", "Surgical Lighting", "外科与内镜",
       ["Light, Surgical", "Surgical Light", "Headlight", "Examination Light"],
       "手术无影灯、头灯与检查照明。"),
    _f("surg_microscope", "手术显微镜", "Surgical Microscopes", "外科与内镜",
       ["Microscope", "Operating Microscope", "Surgical Microscope"],
       "手术显微镜、眼科/神经外科显微系统。"),
    _f("surg_suture", "缝合线与缝合器械", "Sutures and Closure Devices", "外科与内镜",
       ["Suture", "Ligature", "Surgical Clip", "Ligating Clip", "Suture Needle"],
       "可吸收/不可吸收缝线、缝合针与结扎夹。"),
    _f("surg_anastomosis", "吻合与血管夹", "Anastomosis and Vascular Clips", "外科与内镜",
       ["Anastomosis", "Vascular Clip", "Hemoclip"],
       "血管吻合器、吻合夹与血管阻断夹。"),
    # ------------------------------------------------------------------ 眼科
    _f("oph_iol", "人工晶状体", "Intraocular Lenses", "眼科",
       ["Intraocular Lens", "IOL"],
       "单焦/多焦/散光矫正人工晶状体与悬吊式 IOL。"),
    _f("oph_contact", "隐形眼镜与护理产品", "Contact Lenses and Care", "眼科",
       ["Contact Lens", "Lenses, Soft Contact", "Rigid Gas Permeable", "Contact Lens Care"],
       "软性/硬性隐形眼镜、角膜塑形镜与护理液。"),
    _f("oph_retina", "眼底与视网膜手术", "Retina and Vitreous Surgery", "眼科",
       ["Vitrectomy", "Retinal", "Photocoagulation", "Retina", "Silicone Oil", "Intraocular Gas"],
       "玻璃体切割、视网膜激光、眼内填充物与眼底手术器械。"),
    _f("oph_glaucoma", "青光眼治疗装置", "Glaucoma Devices", "眼科",
       ["Glaucoma", "Intraocular Pressure", "Trabecular", "Trabeculoplasty", "Aqueous Shunt"],
       "青光眼引流阀/支架、小梁消融与眼压监测。"),
    _f("oph_refractive", "屈光手术设备与耗材", "Refractive Surgery", "眼科",
       ["Laser, Refractive", "Refractive Surgery", "LASIK", "Femtosecond Laser", "Keratome",
        "Photorefractive"],
       "飞秒/准分子激光、角膜板层刀与屈光手术耗材。"),
    _f("oph_cataract", "白内障手术器械与耗材", "Cataract Surgery", "眼科",
       ["Phacoemulsification", "Cataract", "Capsulorhexis", "Ophthalmic Viscoelastic"],
       "超声乳化仪、粘弹剂、劈核与撕囊器械。"),
    _f("oph_general", "眼科检查与手术器械", "Ophthalmic Diagnostics and Instruments", "眼科",
       ["Ophthalmic", "Ophthalmoscope", "Slit Lamp", "Tonometer", "Corneal", "Perimete"],
       "裂隙灯、眼压计、检眼镜、角膜地形图与眼科手术器械。"),
    # ------------------------------------------------------------------ 口腔
    _f("dent_implant", "牙种植体与基台", "Dental Implants and Abutments", "口腔",
       ["Endosseous", "Dental Implant", "Abutment, Implant, Dental", "Dental Implant Abutment"],
       "牙种植体、基台、骨增量与种植修复部件。"),
    _f("dent_ortho", "正畸矫治器与附件", "Orthodontic Appliances", "口腔",
       ["Aligner", "Orthodontic", "Bracket", "Archwire", "Clear Aligner"],
       "隐形矫治器、托槽、弓丝与正畸附件。"),
    _f("dent_restorative", "口腔修复材料", "Dental Restorative Materials", "口腔",
       ["Tooth Shade", "Porcelain", "Denture", "Dental Resin", "Restorative", "Dental Ceramic",
        "Dental Composite"],
       "树脂、瓷粉、义齿基托与牙冠桥修复材料。"),
    _f("dent_endodontic", "根管治疗材料与器械", "Endodontic Materials", "口腔",
       ["Root Canal", "Endodontic", "Gutta Percha", "Dental Pulp"],
       "根管锉、牙胶尖、根管封闭剂与牙髓治疗材料。"),
    _f("dent_equipment", "牙科设备与器械", "Dental Equipment", "口腔",
       ["Dental Unit", "Dental Chair", "Dental Handpiece", "Dental Drill", "Dental Laser",
        "Dental Operating"],
       "牙科综合治疗台、手机、种植机与牙科激光。"),
    _f("dent_hygiene", "口腔卫生与预防", "Oral Hygiene", "口腔",
       ["Toothbrush", "Dental Floss", "Prophylaxis", "Dental Cleaning", "Oral Irrigator"],
       "牙刷、冲牙器、牙线与预防性洁治产品。"),
    # ------------------------------------------------------------------ 耳鼻喉
    _f("ent_cochlear", "人工耳蜗与听觉植入", "Cochlear and Auditory Implants", "耳鼻喉",
       ["Cochlear", "Auditory Implant", "Hearing Implant"],
       "人工耳蜗、骨锚式助听植入与听觉脑干植入。"),
    _f("ent_sinus", "鼻窦与耳鼻喉手术", "Sinus and ENT Surgery", "耳鼻喉",
       ["Sinus", "Rhinology", "Otolaryngology", "Tonsil", "Adenoid", "Laryngoscope", "Tympanostomy",
        "Septoplasty"],
       "鼻窦内镜、扁桃体/腺样体器械、喉镜与鼓膜置管。"),
    _f("ent_hearing", "助听与听力检测", "Hearing Aids and Audiometry", "耳鼻喉",
       ["Hearing Aid", "Audiometer", "Tympanometer", "Otoacoustic"],
       "助听器、听力计、声导抗与耳声发射检测。"),
    _f("ent_other", "耳鼻喉其他", "Other ENT Devices", "耳鼻喉",
       ["Ear, Nose", "Nasal", "Tracheostomy", "Epistaxis"],
       "鼻腔填塞、气管套管等耳鼻喉通用器械。"),
    # ------------------------------------------------------------------ 泌尿
    _f("uro_stone", "泌尿结石与碎石", "Urologic Stone Management", "泌尿",
       ["Lithotripsy", "Lithotriptor", "Ureteral Stone", "Stone Retrieval"],
       "体外冲击波碎石、输尿管镜碎石与取石器械。"),
    _f("uro_endoscope", "泌尿内镜", "Urologic Endoscopes", "泌尿",
       ["Ureteroscope", "Cystoscope", "Nephroscope", "Ureteroscopy"],
       "输尿管软/硬镜、膀胱镜与肾镜。"),
    _f("uro_continence", "尿失禁与盆底调节", "Urinary Incontinence Devices", "泌尿",
       ["Incontinence", "Pelvic Floor", "Sacral Neuromodulation"],
       "尿失禁吊带、盆底电刺激与骶神经调节。"),
    _f("uro_prostate", "前列腺治疗", "Prostate Treatment Devices", "泌尿",
       ["Prostate", "Prostatic", "BPH", "TURP"],
       "前列腺增生消融、水蒸气热疗与 TURP 器械。"),
    _f("uro_implant", "泌尿植入物（假体/吊带）", "Urologic Implants", "泌尿",
       ["Penis", "Penile", "Urethral Sling", "Sling", "Testicular"],
       "阴茎假体、人工尿道括约肌与吊带。"),
    _f("uro_drain", "泌尿引流与导管", "Urinary Drainage", "泌尿",
       ["Urethral Catheter", "Ureteral Stent", "Nephrostomy", "Urinary Catheter", "Suprapubic"],
       "导尿管、输尿管支架与肾造瘘引流。"),
    # -------------------------------------------------------------- 女性健康
    _f("wh_ablation", "子宫内膜消融", "Endometrial Ablation", "女性健康",
       ["Endometrial Ablation", "Endometrial"],
       "子宫内膜射频/热球消融治疗月经过多。"),
    _f("wh_contraception", "避孕与月经健康", "Contraception and Menstrual Health", "女性健康",
       ["Contraceptive", "Intrauterine Device", "IUD", "Tampon", "Menstrual", "Pessary"],
       "宫内节育器、避孕器械、月经杯与阴道子宫托。"),
    _f("wh_delivery", "产科与分娩", "Obstetric and Delivery Devices", "女性健康",
       ["Obstetric", "Delivery", "Fetal", "Perinatal", "Amniotic", "Labor", "Episiotomy",
        "Vacuum Extraction"],
       "产钳/胎吸、分娩监护、羊膜与产科手术耗材。"),
    _f("wh_gynecology", "妇科手术与诊断", "Gynecologic Surgery and Diagnostics", "女性健康",
       ["Gynecologic", "Vaginal", "Colposcope", "Reproductive", "Ovarian", "Uterine"],
       "阴道镜、宫腔镜、妇科电切与生殖医学器械。"),
    _f("wh_breast_pump", "吸奶器与母乳喂养", "Breast Pumps", "女性健康",
       ["Breast Pump", "Lactation", "Milk"],
       "电动/手动吸奶器与母乳收集产品。"),
    # -------------------------------------------------------------- 呼吸与麻醉
    _f("resp_ventilator", "呼吸机与无创通气", "Ventilators", "呼吸与麻醉",
       ["Ventilator", "Respirator", "CPAP", "BIPAP", "High Frequency Ventilation", "Non-Continuous"],
       "有创/无创呼吸机、高频通气与家用呼吸支持设备。"),
    _f("resp_anesthesia", "麻醉机与麻醉系统", "Anesthesia Machines", "呼吸与麻醉",
       ["Anesthesia", "Anesthetic", "Gas Machine", "Vaporizer", "Breathing Circuit",
        "Anesthesia Machine"],
       "麻醉机、挥发罐、呼吸回路与麻醉深度监测。"),
    _f("resp_airway", "气道管理（插管/喉罩）", "Airway Management", "呼吸与麻醉",
       ["Tracheal Tube", "Endotracheal", "Laryngeal Mask", "Airway", "Supraglottic", "Oropharyngeal"],
       "气管插管、喉罩、口咽/鼻咽通气道与气管切开套管。"),
    _f("resp_therapy", "雾化与呼吸治疗", "Nebulizers and Respiratory Therapy", "呼吸与麻醉",
       ["Nebulizer", "Aerosol", "Humidifier", "Respiratory Therapy", "Metered Dose Inhaler"],
       "雾化器、加湿器与吸入治疗装置。"),
    _f("resp_oxygen", "氧疗与制氧", "Oxygen Therapy and Concentrators", "呼吸与麻醉",
       ["Oxygen Concentrator", "Oxygen Therapy", "Oxygen, Portable", "Liquid Oxygen", "Oxygen Supply"],
       "制氧机、液氧与便携氧疗设备。"),
    _f("resp_sleep", "睡眠呼吸与抗鼾", "Sleep Apnea and Anti-Snoring", "呼吸与麻醉",
       ["Sleep Apnea", "Anti-Snoring", "Snoring", "Upper Airway Stimulation"],
       "睡眠呼吸暂停诊断、CPAP 面罩与抗鼾装置。"),
    _f("resp_pulm", "肺功能与呼吸诊断", "Pulmonary Function Diagnostics", "呼吸与麻醉",
       ["Spirometer", "Pulmonary Function", "Capnograph", "Respiratory Monitor", "Ventilatory Effort"],
       "肺功能仪、二氧化碳监测与呼吸力学检测。"),
    # -------------------------------------------------------------- 患者监护
    _f("mon_multiparameter", "多参数监护仪", "Multiparameter Patient Monitors", "患者监护",
       ["Physiological Monitor", "Patient Monitor", "Multiparameter", "Monitor, Physiological"],
       "床旁/中央站多参数监护仪与模块化监护系统。"),
    _f("mon_bp", "血压监测", "Blood Pressure Monitoring", "患者监护",
       ["Blood-Pressure", "Blood Pressure", "Sphygmomanometer", "Pressure Transducer"],
       "无创/有创血压监测、电子血压计与压力传感器。"),
    _f("mon_spo2", "血氧与脉搏血氧", "Pulse Oximetry", "患者监护",
       ["Oximeter", "Pulse Oximeter", "Co-Oximeter", "SPO2"],
       "指夹式/床旁脉搏血氧仪与血氧探头。"),
    _f("mon_temp", "体温监测", "Temperature Monitoring", "患者监护",
       ["Thermometer", "Temperature Monitor", "Continuous Measurement Thermometer"],
       "电子体温计、连续体温监测与红外测温。"),
    _f("mon_fetal", "胎心与围产监护", "Fetal and Perinatal Monitoring", "患者监护",
       ["Fetal Monitor", "Tocodynamometer", "Perinatal", "Ultrasound, Obstetric", "Fetal Heart"],
       "胎心监护仪、宫缩监测与围产期监护。"),
    _f("mon_neuro", "神经电生理监测", "Neurophysiologic Monitoring", "患者监护",
       ["Electroencephalograph", "EEG", "Evoked Response", "Nerve Conduction", "Electromyograph",
        "Neurophysiologic"],
       "脑电图、诱发电位、肌电图与术中神经监测。"),
    _f("mon_hemodynamic", "血流动力学监测", "Hemodynamic Monitoring", "患者监护",
       ["Hemodynamic", "Cardiac Output", "Catheter, Hemodynamic", "Pressure Monitoring"],
       "心输出量、Swan-Ganz 与血流动力学监测系统。"),
    # ------------------------------------------------------------ 输注与糖尿病
    _f("inf_pump", "输液泵与输注系统", "Infusion Pumps", "输注与糖尿病",
       ["Infusion Pump", "Pump, Infusion", "Syringe Pump", "Elastomeric Pump", "Volumetric Pump"],
       "容积/注射/弹性输液泵与疼痛管理输注系统。"),
    _f("inf_implant_pump", "植入式输注泵", "Implantable Infusion Pumps", "输注与糖尿病",
       ["Implanted, Programmable", "Implantable Infusion", "Intrathecal Pump", "Pump, Infusion, Implanted"],
       "鞘内/静脉植入式程控泵（疼痛、痉挛）。"),
    _f("inf_set", "输液器与输注管路", "Infusion Sets and Tubing", "输注与糖尿病",
       ["Administration Set", "I.V. Set", "Infusion Set", "IV Set", "Fluid Transfer"],
       "输液器、延长管、三通与输注管路。"),
    _f("inf_vascular_access", "中心静脉与输液港", "Central Venous Access and Ports", "输注与糖尿病",
       ["Vascular Access Port", "Central Venous", "PICC", "Catheter, Central", "Port, Vascular",
        "Implantable Port"],
       "CVC、PICC、输液港与中心静脉导管。"),
    _f("inj_syringe", "注射器与针头", "Syringes and Needles", "输注与糖尿病",
       ["Syringe", "Hypodermic Needle", "Needle, Hypodermic", "Injection Needle", "Autoinjector",
        "Injector And Syringe", "Blood Lancet"],
       "注射器、注射针、胰岛素笔用针与采血针。"),
    _f("diab_cgm", "持续血糖监测（CGM）", "Continuous Glucose Monitoring", "输注与糖尿病",
       ["Glucose Sensor", "Continuous Glucose", "CGM", "Glucose Monitoring"],
       "CGM 传感器、发射器与动态血糖管理系统。"),
    _f("diab_insulin", "胰岛素泵与闭环输注", "Insulin Pumps and Closed-Loop", "输注与糖尿病",
       ["Automated Insulin Dosing", "Insulin Pump", "Insulin Infusion", "Closed Loop"],
       "胰岛素泵、混合闭环（HCL）与自动胰岛素输注。"),
    _f("diab_glucose", "血糖检测仪与试纸", "Blood Glucose Meters and Strips", "输注与糖尿病",
       ["Blood Glucose", "Glucose Test", "Glucometer", "Glucose Oxidase"],
       "指尖血糖仪、试纸与医院血糖检测系统。"),
    _f("diab_consumable", "糖尿病其他耗材", "Other Diabetes Consumables", "输注与糖尿病",
       ["Insulin Pen", "Insulin Syringe", "Lancet"],
       "胰岛素笔、注射器与采血耗材。"),
    # ------------------------------------------------------------ 肾脏与透析
    _f("dial_dialyzer", "透析器与透析机", "Dialyzers and Dialysis Machines", "肾脏与透析",
       ["Dialyzer", "Hemodialysis", "Dialysis Machine", "Peritoneal Dialysis", "Hemodiafiltration"],
       "血液透析器、透析机、腹膜透析与 CRRT 设备。"),
    _f("dial_access", "透析血管通路", "Dialysis Access", "肾脏与透析",
       ["Dialysis Access", "Arteriovenous", "AV Fistula", "Fistula Needle"],
       "动静脉内瘘穿刺针、AV 移植物与透析通路维护。"),
    _f("dial_catheter", "透析导管", "Dialysis Catheters", "肾脏与透析",
       ["Hemodialysis Catheter", "Dialysis Catheter", "Tunneled Catheter"],
       "带 cuff 透析导管、隧道式与临时透析导管。"),
    # ------------------------------------------------------------ 伤口与止血
    _f("wound_dressing", "伤口敷料", "Wound Dressings", "伤口与止血",
       ["Dressing", "Wound Dressing", "Bandage", "Gauze", "Wound Cover"],
       "泡沫/水胶体/银离子/藻酸盐敷料、纱布与绷带。"),
    _f("wound_npwt", "负压伤口治疗", "Negative Pressure Wound Therapy", "伤口与止血",
       ["Negative Pressure Wound", "Vacuum Assisted Closure", "NPWT"],
       "负压伤口治疗泵、敷料与吸引套装。"),
    _f("wound_hemostat", "可吸收止血材料", "Absorbable Hemostats", "伤口与止血",
       ["Absorbable Hemostatic", "Hemostatic Agent", "Hemostat", "Collagen Hemostatic", "Thrombin"],
       "可吸收止血纱/海绵、胶原与凝血酶止血材料。"),
    _f("wound_sealant", "医用封合剂与粘合剂", "Sealants and Adhesives", "伤口与止血",
       ["Sealant", "Adhesive", "Fibrin Glue", "Cyanoacrylate", "Polymerizing"],
       "纤维蛋白胶、氰基丙烯酸酯胶与手术封合剂。"),
    _f("wound_skin", "皮肤替代物与烧伤修复", "Skin Substitutes and Burn Care", "伤口与止血",
       ["Skin Substitute", "Burn", "Dermal Substitute", "Wound Matrix", "Graft, Skin"],
       "人工真皮、皮肤替代物、烧伤敷料与植皮材料。"),
    _f("wound_mesh", "外科补片与疝修补", "Surgical Mesh and Hernia Repair", "伤口与止血",
       ["Mesh, Surgical", "Hernia", "Surgical Mesh", "Adhesion Barrier"],
       "疝修补补片、防粘连屏障与盆底补片。"),
    # ------------------------------------------------------------ 康复与辅助
    _f("rehab_wheelchair", "轮椅与代步车", "Wheelchairs and Scooters", "康复与辅助",
       ["Wheelchair", "Scooter", "Motorized 3-Wheeled"],
       "手动/电动轮椅、代步车与轮椅配件。"),
    _f("rehab_exo", "外骨骼与康复机器人", "Exoskeletons and Rehab Robots", "康复与辅助",
       ["Exoskeleton", "Rehabilitation Robot", "Gait Training", "Powered Exoskeleton"],
       "下肢/上肢外骨骼、步态训练与康复机器人。"),
    _f("rehab_therapy", "理疗与康复设备", "Physical Therapy Equipment", "康复与辅助",
       ["Massager", "Diathermy", "Ultrasound Therapy", "Traction", "Continuous Passive Motion",
        "Paraffin"],
       "理疗仪、热疗/电疗、牵引床与 CPM 康复设备。"),
    _f("rehab_orthosis", "矫形器与支具", "Orthoses and Prostheses", "康复与辅助",
       ["Orthosis", "Brace", "Splint", "Prosthetic Limb", "Artificial Limb", "Compression Stocking",
        "Sleeve, Limb"],
       "矫形支具、假肢、压力袜与淋巴水肿治疗。"),
    _f("rehab_mobility", "助行与转移辅具", "Mobility and Transfer Aids", "康复与辅助",
       ["Walker", "Crutch", "Cane", "Patient Lift", "Transfer Aid"],
       "助行器、拐杖、病人移位机与转移辅具。"),
    _f("rehab_bed", "病床与压力管理", "Beds and Pressure Management", "康复与辅助",
       ["Bed", "Mattress", "Stretcher", "Patient Positioning", "Overbed"],
       "医用病床、防压疮床垫、担架与体位管理。"),
    # ------------------------------------------------------------ 医美与整形
    _f("aes_filler", "皮肤填充剂与注射美容", "Dermal Fillers and Injectables", "医美与整形",
       ["Dermal Implant", "Dermal Filler", "Hyaluronic Acid", "Filler", "Collagen Injectable",
        "Microneedling", "Botulinum"],
       "玻尿酸/胶原填充剂、微针与肉毒素注射器械。"),
    _f("aes_laser", "激光与强脉冲光美肤", "Aesthetic Lasers and IPL", "医美与整形",
       ["Hair Removal", "Wrinkle", "Skin Rejuvenation", "Light Based", "Intense Pulsed Light", "IPL",
        "Tattoo Removal"],
       "脱毛、嫩肤、祛皱与文身去除的激光/IPL 设备。"),
    _f("aes_body", "吸脂与身体塑形", "Liposuction and Body Contouring", "医美与整形",
       ["Liposuction", "Lipoplasty", "Body Contouring", "Cryolipolysis", "RF Lysis"],
       "负压/水动力吸脂、冷冻溶脂与射频塑形。"),
    _f("aes_breast", "乳房植入物与扩张器", "Breast Implants and Expanders", "医美与整形",
       ["Prosthesis, Breast", "Breast Implant", "Tissue Expander"],
       "硅胶/盐水乳房假体与组织扩张器。"),
    # -------------------------------------------------- 感染控制与医院耗材
    _f("hosp_glove", "医用手套", "Medical Gloves", "感染控制与医院耗材",
       ["Glove", "Examination Glove", "Surgeon'S Gloves"],
       "检查手套、外科手套与丁腈/乳胶手套。"),
    _f("hosp_mask", "口罩与呼吸防护", "Masks and Respiratory Protection", "感染控制与医院耗材",
       ["Mask, Surgical", "Face Mask", "N95", "Surgical Mask", "Dust Mask"],
       "外科口罩、N95/KN95 与防护面罩。"),
    _f("hosp_protective", "防护服与隔离用品", "Protective Apparel", "感染控制与医院耗材",
       ["Isolation Gown", "Protective", "Coverall", "Face Shield", "Goggle", "Barrier"],
       "隔离衣、防护服、护目镜与面屏。"),
    _f("hosp_sterilization", "灭菌设备与监测", "Sterilization Equipment and Monitoring", "感染控制与医院耗材",
       ["Sterilizer", "Sterilization", "Autoclave", "Biological Indicator", "Sterilization Wrap",
        "Ethylene Oxide", "Sterilization Container"],
       "高压蒸汽/环氧乙烷灭菌器、灭菌包装与生物指示剂。"),
    _f("hosp_disinfection", "消毒与清洁", "Disinfection and Cleaning", "感染控制与医院耗材",
       ["Disinfectant", "Sanitizer", "Antiseptic", "High-Level Disinfection", "Cleaner"],
       "医用消毒剂、手消、物表消毒与清洗设备。"),
    _f("hosp_general", "医院通用耗材与器具", "General Hospital Supplies", "感染控制与医院耗材",
       ["General Hospital", "Utility", "Container", "Spill Kit", "Applicator", "Swab", "Sponge", "Bag",
        "Linen", "Sheet"],
       "通用护理耗材、容器、棉签、铺巾与医用袋。"),
    _f("hosp_iv_supplies", "静脉输液耗材", "Intravenous Supplies", "感染控制与医院耗材",
       ["Intravenous", "IV Fluid", "Infusion Bag", "Saline", "IV Administration"],
       "输液袋、生理盐水、静脉营养与输液附件。"),
    # ---------------------------------------------------------------- 数字医疗
    _f("digital_clinical", "临床诊断决策软件", "Clinical Decision Software", "数字医疗",
       ["Computer, Diagnostic", "Clinical Decision", "Diagnostic Software", "Decision Support"],
       "诊断决策支持、临床路径与风险预测软件。"),
    _f("digital_remote", "远程医疗与数字疗法", "Telehealth and Digital Therapeutics", "数字医疗",
       ["Remote", "Telemedicine", "Digital Therapeutic", "Mobile Medical Application"],
       "远程监护平台、数字疗法与移动医疗应用。"),
    # ---------------------------------------------------- 专科兜底（低置信度）
    _f("fb_general_hospital", "其他医院通用器械（按专科兜底）", "Other General Hospital Devices", "感染控制与医院耗材",
       [], "仅按 FDA 专科 General Hospital 归档，未做产品细分，低置信度。"),
    _f("fb_general_surgery", "其他普外/整形器械（按专科兜底）", "Other General and Plastic Surgery Devices", "外科与内镜",
       [], "仅按 FDA 专科 General, Plastic Surgery 归档，未做产品细分，低置信度。"),
    _f("fb_cardio", "其他心血管器械（按专科兜底）", "Other Cardiovascular Devices", "心血管",
       [], "仅按 FDA 专科 Cardiovascular 归档，未做产品细分，低置信度。"),
    _f("fb_ortho", "其他骨科器械（按专科兜底）", "Other Orthopedic Devices", "骨科",
       [], "仅按 FDA 专科 Orthopedic 归档，未做产品细分，低置信度。"),
    _f("fb_imaging", "其他影像设备（按专科兜底）", "Other Radiology Devices", "影像与放疗",
       [], "仅按 FDA 专科 Radiology 归档，未做产品细分，低置信度。"),
    _f("fb_giuro", "其他消化/泌尿器械（按专科兜底）", "Other Gastroenterology/Urology Devices", "泌尿",
       [], "仅按 FDA 专科 Gastroenterology, Urology 归档，未做产品细分，低置信度。"),
    _f("fb_dental", "其他口腔器械（按专科兜底）", "Other Dental Devices", "口腔",
       [], "仅按 FDA 专科 Dental 归档，未做产品细分，低置信度。"),
    _f("fb_obgyn", "其他妇产器械（按专科兜底）", "Other OB/GYN Devices", "女性健康",
       [], "仅按 FDA 专科 Obstetrics/Gynecology 归档，未做产品细分，低置信度。"),
    _f("fb_anes", "其他麻醉器械（按专科兜底）", "Other Anesthesiology Devices", "呼吸与麻醉",
       [], "仅按 FDA 专科 Anesthesiology 归档，未做产品细分，低置信度。"),
    _f("fb_oph", "其他眼科器械（按专科兜底）", "Other Ophthalmic Devices", "眼科",
       [], "仅按 FDA 专科 Ophthalmic 归档，未做产品细分，低置信度。"),
    _f("fb_rehab", "其他康复理疗器械（按专科兜底）", "Other Physical Medicine Devices", "康复与辅助",
       [], "仅按 FDA 专科 Physical Medicine 归档，未做产品细分，低置信度。"),
    _f("fb_ent", "其他耳鼻喉器械（按专科兜底）", "Other ENT Devices", "耳鼻喉",
       [], "仅按 FDA 专科 Ear, Nose, Throat 归档，未做产品细分，低置信度。"),
    _f("fb_ivd", "其他体外诊断试剂（按专科兜底）", "Other IVD Products", "体外诊断",
       [], "仅按 FDA 检验类专科归档，未做产品细分，低置信度。"),
    _f("fb_neuro", "其他神经科器械（按专科兜底）", "Other Neurology Devices", "神经调控与神经外科",
       [], "仅按 FDA 专科 Neurology 归档，未做产品细分，低置信度。"),
]

# Specialty (FDA medical_specialty_description) -> fallback family. Ordered:
# first substring match wins, so longer / more specific phrases come first.
FALLBACK_SPECIALTIES: list[tuple[str, str]] = [
    ("General, Plastic Surgery", "fb_general_surgery"),
    ("Gastroenterology, Urology", "fb_giuro"),
    ("Ear, Nose, Throat", "fb_ent"),
    ("General Hospital", "fb_general_hospital"),
    ("Cardiovascular", "fb_cardio"),
    ("Orthopedic", "fb_ortho"),
    ("Radiology", "fb_imaging"),
    ("Dental", "fb_dental"),
    ("Obstetrics/Gynecology", "fb_obgyn"),
    ("Anesthesiology", "fb_anes"),
    ("Ophthalmic", "fb_oph"),
    ("Physical Medicine", "fb_rehab"),
    ("Microbiology", "fb_ivd"),
    ("Clinical Chemistry", "fb_ivd"),
    ("Hematology", "fb_ivd"),
    ("Immunology", "fb_ivd"),
    ("Pathology", "fb_ivd"),
    ("Clinical Toxicology", "fb_ivd"),
    ("Medical Genetics", "fb_ivd"),
    ("Neurology", "fb_neuro"),
]

_RULES: list[tuple[int, int, str, str]] | None = None


def family_specs(include_fallback: bool = True) -> list[dict[str, Any]]:
    specs = [dict(spec) for spec in FAMILY_SPECS]
    if not include_fallback:
        specs = [spec for spec in specs if spec["keywords"]]
    return specs


def _rules() -> list[tuple[int, int, str, str]]:
    """Pre-sorted (length, order, normalised keyword, family id) match table."""
    global _RULES
    if _RULES is None:
        rules: list[tuple[int, int, str, str]] = []
        for order, spec in enumerate(FAMILY_SPECS):
            for keyword in spec["keywords"]:
                normalised = norm_text(keyword)
                if len(normalised) >= 4:  # 3-letter keys cause false positives
                    rules.append((len(normalised), order, normalised, spec["id"]))
        rules.sort(key=lambda rule: (-rule[0], rule[1]))
        _RULES = rules
    return _RULES


def _best_match(text: str, rules: list[tuple[int, int, str, str]]) -> tuple[str, int] | None:
    """Longest-keyword match inside ``text``; ``None`` on no match.

    Returns a 2-tuple even for a conflict - the caller detects it by matching
    several family ids at the winning length.
    """
    if not text:
        return None
    best_len = 0
    winners: list[str] = []
    for length, _order, keyword, family_id in rules:
        if best_len and length < best_len:
            break
        if keyword in text:
            if length > best_len:
                best_len, winners = length, [family_id]
            elif length == best_len and family_id not in winners:
                winners.append(family_id)
    if not winners:
        return None
    return winners[0], best_len


def _ambiguous(text: str, rules: list[tuple[int, int, str, str]]) -> list[str]:
    """All family ids matching ``text`` at the winning keyword length."""
    if not text:
        return []
    best_len = 0
    winners: list[str] = []
    for length, _order, keyword, family_id in rules:
        if best_len and length < best_len:
            break
        if keyword in text:
            if length > best_len:
                best_len, winners = length, [family_id]
            elif length == best_len and family_id not in winners:
                winners.append(family_id)
    return winners


def _fallback_family(specialty: str | None) -> str | None:
    text = (specialty or "").strip()
    if not text:
        return None
    lowered = text.lower()
    for needle, family_id in FALLBACK_SPECIALTIES:
        if needle.lower() in lowered:
            return family_id
    return None


def assign_codes(
    rows: Iterable[Mapping[str, Any]],
    specs: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, str], list[str], dict[str, str]]:
    """Map product codes to families.

    Returns ``(code_to_family, unclassified_codes, unclassified_reasons)``.
    Assignment order: generic-name keyword > definition keyword > specialty
    fallback > unclassified.
    """
    use_specs = [dict(spec) for spec in (specs or FAMILY_SPECS)]
    known = {spec["id"] for spec in use_specs}
    rules: list[tuple[int, int, str, str]] = []
    for order, spec in enumerate(use_specs):
        for keyword in spec.get("keywords", []):
            normalised = norm_text(keyword)
            if len(normalised) >= 4:
                rules.append((len(normalised), order, normalised, spec["id"]))
    rules.sort(key=lambda rule: (-rule[0], rule[1]))

    code_map: dict[str, str] = {}
    unclassified: list[str] = []
    reasons: dict[str, str] = {}
    for row in sorted(rows, key=lambda item: str(item.get("product_code") or "")):
        code = str(row.get("product_code") or "").strip()
        if not code:
            continue
        name = norm_text(row.get("device_name"))
        definition = norm_text(row.get("definition"))
        winners = _ambiguous(name, rules)
        if not winners and definition:
            winners = _ambiguous(definition, rules)
        if len(winners) == 1 and winners[0] in known:
            code_map[code] = winners[0]
            continue
        if len(winners) > 1:
            unclassified.append(code)
            reasons[code] = "ambiguous:" + ",".join(sorted(winners))
            continue
        fallback = _fallback_family(row.get("specialty"))
        if fallback and fallback in known:
            code_map[code] = fallback
            continue
        unclassified.append(code)
        reasons[code] = "no_match"
    return code_map, unclassified, reasons


# --------------------------------------------------------------------------- build
def _family_index() -> dict[str, dict[str, Any]]:
    return {spec["id"]: spec for spec in FAMILY_SPECS}


def build_families(
    db,
    write: bool = True,
    path=None,
    min_families: int = MIN_FAMILIES,
    max_families: int = MAX_FAMILIES,
) -> dict[str, Any]:
    """Cluster ``product_codes`` into the curated family taxonomy.

    Pure function of (database rows, curated specs): the same DB always yields
    the same JSON. ``write=False`` is used by tests so the offline suite never
    touches ``config/``.
    """
    rows = db.query(
        "SELECT product_code, device_name, definition, specialty, track_id FROM product_codes"
    )
    code_map, unclassified, reasons = assign_codes(rows)

    by_id: dict[str, list[str]] = defaultdict(list)
    for code, family_id in code_map.items():
        by_id[family_id].append(code)

    families: list[dict[str, Any]] = []
    for spec in FAMILY_SPECS:
        codes = sorted(by_id.get(spec["id"], []))
        if not codes:
            continue
        families.append(
            {
                "id": spec["id"],
                "name_zh": spec["name_zh"],
                "name_en": spec["name_en"],
                "category": spec["category"],
                "keywords": list(spec["keywords"]),
                "codes": codes,
                "note": spec["note"],
            }
        )
    category_pos = {name: pos for pos, name in enumerate(CATEGORY_ORDER)}
    families.sort(
        key=lambda item: (
            category_pos.get(item["category"], len(CATEGORY_ORDER)),
            -len(item["codes"]),
            item["id"],
        )
    )

    # ---- coverage measured on real events (honest denominators, see meta)
    coded = db.query(
        "SELECT product_code, COUNT(*) AS n FROM events"
        " WHERE product_code IS NOT NULL AND product_code != ''"
        " GROUP BY product_code"
    )
    coded_total = sum(int(row["n"]) for row in coded)
    unclassified_events = sum(
        int(row["n"]) for row in coded if str(row["product_code"]) not in code_map
    )
    classified_events = coded_total - unclassified_events
    events_total = int(db.scalar("SELECT COUNT(*) FROM events", default=0) or 0)

    family_events = Counter()
    for row in coded:
        code = str(row["product_code"])
        family_id = code_map.get(code)
        if family_id:
            family_events[family_id] += int(row["n"])
    ranked = family_events.most_common()
    top20_events = sum(n for _family, n in ranked[:20])

    reason_counts = Counter(reasons.values())
    meta = {
        "build": BUILD_ID,
        "family_count": len(families),
        "category_count": len({item["category"] for item in families}),
        "code_total": len(rows),
        "classified_codes": len(code_map),
        "unclassified_codes": len(unclassified),
        "coverage": {
            # Primary denominator: device events that carry a product code.
            # Drug approvals and CT.gov trials have no product code and can
            # never be covered by a product family, so they are reported
            # separately instead of inflating the "missed" share.
            "coded_events": coded_total,
            "classified_events": classified_events,
            "classified_share": round(_share(classified_events, coded_total), 4),
            "unclassified_events": unclassified_events,
            "unclassified_share": round(_share(unclassified_events, coded_total), 4),
            "all_events": events_total,
            "classified_share_of_all_events": round(_share(classified_events, events_total), 4),
            "top20_events": top20_events,
            "top20_share": round(_share(top20_events, coded_total), 4),
            "top20_share_of_all_events": round(_share(top20_events, events_total), 4),
        },
        "unclassified_reasons": {
            "ambiguous": reason_counts.get("ambiguous", 0) + sum(
                count for key, count in reason_counts.items() if key.startswith("ambiguous:")
            ),
            "no_match": reason_counts.get("no_match", 0),
        },
    }
    payload = {"meta": meta, "families": families, "unclassified": unclassified}
    if len(families) < min_families or len(families) > max_families:
        payload["meta"]["family_count_warning"] = (
            f"期望 {min_families}-{max_families} 个族，实际 {len(families)}"
        )
    if write:
        write_json(path or FAMILIES_FILE, payload)
    return payload


def _share(part: float, total: float) -> float:
    return float(part) / float(total) if total else 0.0


def load_families(path=None) -> dict[str, Any]:
    """Read ``config/product_families.json`` (generated artifact)."""
    payload = read_json(path or FAMILIES_FILE)
    if not isinstance(payload, dict):
        return {"meta": {}, "families": [], "unclassified": []}
    payload.setdefault("meta", {})
    payload.setdefault("families", [])
    payload.setdefault("unclassified", [])
    return payload


def family_lookup(payload: Mapping[str, Any] | None = None) -> tuple[dict[str, dict], dict[str, str]]:
    """Return ``(families_by_id, code_to_family_id)`` for a generated payload."""
    data = payload if payload is not None else load_families()
    by_id: dict[str, dict[str, Any]] = {}
    code_map: dict[str, str] = {}
    for family in data.get("families", []):
        family_id = str(family.get("id") or "")
        if not family_id:
            continue
        by_id[family_id] = family
        for code in family.get("codes", []):
            code_map[str(code)] = family_id
    return by_id, code_map


def coverage_report(payload: Mapping[str, Any]) -> str:
    """Human-readable coverage report printed by the build script."""
    meta = payload.get("meta", {})
    cov = meta.get("coverage", {})
    lines = [
        f"产品族数量            {meta.get('family_count')}  (类别 {meta.get('category_count')})",
        f"产品码                {meta.get('code_total')}  "
        f"已归类 {meta.get('classified_codes')} / 未归类 {meta.get('unclassified_codes')}",
        f"事件覆盖（主口径）    {cov.get('classified_events')}/{cov.get('coded_events')} "
        f"= {_pct(cov.get('classified_share'))}  （有产品码的事件）",
        f"事件覆盖（全事件）    {_pct(cov.get('classified_share_of_all_events'))}  "
        f"（全库 {cov.get('all_events')} 条，含无产品码的药品/试验事件）",
        f"Top20 族覆盖          {_pct(cov.get('top20_share'))}  （有产品码的事件）"
        f" / {_pct(cov.get('top20_share_of_all_events'))}  （全事件）",
        f"未分类事件            {cov.get('unclassified_events')} "
        f"= {_pct(cov.get('unclassified_share'))}；原因 "
        f"{meta.get('unclassified_reasons', {})}",
    ]
    return "\n".join(lines)


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"
