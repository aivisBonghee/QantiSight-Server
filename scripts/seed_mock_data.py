import sys
import os
import uuid
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal, engine, Base
from app.models import Case, QcResult

Base.metadata.create_all(bind=engine)

SURNAMES = [
    "김","이","박","최","정","강","조","윤","장","임",
    "한","오","서","신","권","황","안","송","류","전",
    "홍","고","문","양","손","배","백","허","유","남",
]
GIVEN_NAMES = [
    "민수","지영","현우","서연","준혁","하은","도윤","수빈","예준","지우",
    "시우","하윤","은서","지호","서준","채원","민재","다은","태현","유진",
]
HOSPITALS = ["SMC", "KUMC", "HALLYM", "SCHMC"]
HOSPITAL_WEIGHTS = [0.3, 0.25, 0.2, 0.25]
STAINS = ["HE", "HER2", "ER", "PR", "KI67"]
ORGANS = ["Breast", "Stomach", "Bladder", "Thyroid", "Colon", "Brain"]
SERVERS = ["server-1", "server-2", "server-3", "server-4", "server-5"]
DIAGNOSES = [
    "Adenocarcinoma", "Squamous cell carcinoma", "Ductal carcinoma in situ",
    "Invasive ductal carcinoma", "Normal tissue", "Chronic inflammation",
    "Benign neoplasm", "Metastatic carcinoma", "Dysplasia", "Hyperplasia",
]
CANCER_DIAGNOSES = {
    "Adenocarcinoma", "Squamous cell carcinoma", "Ductal carcinoma in situ",
    "Invasive ductal carcinoma", "Metastatic carcinoma",
}
SUSPECTED_DISEASES = [
    "Bx malignancy", "Cpp", "R/O adenocarcinoma", "R/O lymphoma",
    "Chronic gastritis", "R/O carcinoma", "Inflammatory bowel disease",
    "R/O metastasis", None, None,
]
IHC_MARKER_SETS = [
    "HER2, ER, PR, Ki-67", "CK7, CK20, CDX2", "CD3, CD20, Ki-67",
    "p53, MLH1, MSH2", "TTF-1, Napsin A", "ER, PR", None, None,
]
MOLECULAR_TESTS = [
    "EGFR mutation", "KRAS mutation", "BRAF V600E", "HER2 FISH",
    "MSI testing", None, None, None,
]
CLINICAL_INFOS = [
    "Upper endoscopy finding: mass at antrum",
    "Colonoscopy: polyp at sigmoid colon",
    "Breast US: 1.5cm mass at left upper outer quadrant",
    "CT: lung nodule RUL 2cm",
    "Renal biopsy for proteinuria evaluation",
    "Follow-up after chemotherapy",
    None, None, None,
]


_used_slide_ids: set[str] = set()

def make_slide_id(hospital: str, year: int) -> str:
    while True:
        if hospital == "SMC":
            sid = f"S {year}G{random.randint(0, 999999):06d}"
        elif hospital == "KUMC":
            sid = f"S{year}{random.randint(0, 999999):06d}"
        else:
            sid = f"S-{year}-{random.randint(0, 99999):05d}"
        if sid not in _used_slide_ids:
            _used_slide_ids.add(sid)
            return sid


def make_qc(case_id: str, stain_type: str, diagnosis: str) -> QcResult:
    focus = max(0, min(100, round(random.gauss(82, 12))))
    stain_q = max(0, min(100, round(random.gauss(78, 15))))
    tissue = max(0, min(100, round(random.gauss(72, 18))))
    organ_match = random.random() < 0.92
    organ_conf = round(0.85 + random.random() * 0.14, 2) if organ_match else round(0.3 + random.random() * 0.3, 2)
    stain_conf = round(0.88 + random.random() * 0.11, 2) if random.random() < 0.95 else round(0.4 + random.random() * 0.3, 2)

    is_cancer = diagnosis in CANCER_DIAGNOSES
    lesion_ratio = round(random.random() * 0.6 + 0.02, 3) if is_cancer else None
    lesion_vol = None
    if lesion_ratio is not None:
        lesion_vol = "Low" if lesion_ratio < 0.1 else "Moderate" if lesion_ratio < 0.3 else "High"

    is_ihc = stain_type in ("HER2", "ER", "PR", "KI67")
    ctrl_present = (random.random() < 0.88) if is_ihc else None
    ctrl_conf = None
    if ctrl_present is not None:
        ctrl_conf = round(0.82 + random.random() * 0.17, 2) if ctrl_present else round(0.2 + random.random() * 0.3, 2)

    match_weight = 20 if organ_match else 0
    overall = min(100, round(focus * 0.3 + stain_q * 0.3 + tissue * 0.2 + match_weight))

    return QcResult(
        id=str(uuid.uuid4()),
        case_id=case_id,
        focus_score=focus,
        stain_quality=stain_q,
        tissue_coverage=tissue,
        overall_qc_score=overall,
        organ_match=organ_match,
        detected_organ="",
        organ_confidence=organ_conf,
        stain_classification=random.choice(STAINS),
        stain_confidence=stain_conf,
        lesion_area_ratio=lesion_ratio,
        lesion_volume=lesion_vol,
        control_tissue_present=ctrl_present,
        control_tissue_confidence=ctrl_conf,
    )


def seed(count: int = 500):
    random.seed(42)
    db = SessionLocal()

    existing = db.query(Case).count()
    if existing > 0:
        print(f"Already {existing} cases in DB. Skipping seed.")
        db.close()
        return

    cases = []
    for i in range(count):
        hospital = random.choices(HOSPITALS, HOSPITAL_WEIGHTS)[0]
        year = 24 + random.randint(0, 2)
        full_year = 2000 + year
        slide_id = make_slide_id(hospital, year)
        organ = random.choice(ORGANS)
        stain = random.choice(STAINS)
        diagnosis = random.choice(DIAGNOSES)
        month = f"{random.randint(1, 12):02d}"
        day = f"{random.randint(1, 28):02d}"

        r = random.random()
        status = "WAITING" if r < 0.1 else "PROCESSING" if r < 0.15 else "ERROR" if r < 0.18 else "DONE"

        case_id = str(uuid.uuid4())
        is_ihc = stain in ("HER2", "ER", "PR", "KI67")
        suspected = random.choice(SUSPECTED_DISEASES)
        req_stains = stain if random.random() < 0.7 else f"{stain},{random.choice(STAINS)}"
        ihc = random.choice(IHC_MARKER_SETS) if is_ihc else None
        mol = random.choice(MOLECULAR_TESTS) if random.random() < 0.3 else None
        clin = random.choice(CLINICAL_INFOS)

        case = Case(
            id=case_id,
            slide_id=slide_id,
            hospital_code=hospital,
            patient_id=f"P-{full_year}{random.randint(0, 99999):05d}",
            patient_name=f"{random.choice(SURNAMES)}{random.choice(GIVEN_NAMES)}",
            exam_no=f"EX{full_year}{random.randint(0, 9999):04d}",
            exam_date=f"{full_year}-{month}-{day}",
            organ=organ,
            stain_type=stain,
            diagnosis=diagnosis,
            status=status,
            server_location=random.choice(SERVERS),
            suspected_disease=suspected,
            requested_stains=req_stains,
            ihc_markers=ihc,
            molecular_test=mol,
            clinical_info=clin,
        )
        cases.append(case)

        if status == "DONE":
            qc = make_qc(case_id, stain, diagnosis)
            detected = organ if qc.organ_match else random.choice([o for o in ORGANS if o != organ])
            qc.detected_organ = detected
            db.add(qc)

    db.add_all(cases)
    db.commit()
    db.close()
    print(f"Seeded {count} cases.")


if __name__ == "__main__":
    seed()
