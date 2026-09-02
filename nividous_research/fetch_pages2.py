"""Second pass: library palette docs, quick starts, and Smart Bot / OCR specifics."""
import re
from html import unescape
from pathlib import Path

import requests

ROOT = "https://community.nividous.com/help-documents/"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"

TARGETS = {
    "configuring_libraries": "Nividous-RPA-Help/User_Interface/Configuring_Dynamic_Palette.htm",
    "rpa_process_components": "Nividous-RPA-Help/User_Interface/RPA_Process_Components.htm",
    "rpa_ui": "Nividous-RPA-Help/User_Interface/The_User_Interface.htm",
    "actions_arguments": "Nividous-RPA-Help/Working_with_Libraries/Providing Arguments to Actions/Types of Arguments.htm",
    "working_with_libraries": "Nividous-RPA-Help/Working_with_Libraries/Providing Arguments to Actions/Working_with_Libraries.htm",
    "nlp_library_rpa": "Nividous-RPA-Help/Working_with_Libraries/Providing Arguments to Actions/Using_NLP_Library.htm",
    "cv_library_rpa": "Nividous-RPA-Help/Working_with_Libraries/Providing Arguments to Actions/Using_CV_Library.htm",
    "queue_framework": "Nividous-RPA-Help/Working_with_Queue_Framework/Working_with_Queue_Framework.htm",
    "best_practices_design": "Nividous-RPA-Help/Best_Practices/Design.htm",
    "rpa_lpa_integration": "Nividous-RPA-Help/Best_Practices/RPA_BPM.htm",
    "lpa_about": "Nividous-LPA-Help/About BPM Studio/About_BPM_Studio.htm",
    "lpa_rpa_task": "Nividous-LPA-Help/RPA_Tasks/RPATask_Adding.htm",
    "lpa_smartbot_templates": "Nividous-LPA-Help/Integrating_BPM_And_Smart_Bot/Working_with_Smart_Bot_Templates.htm",
    "lpa_business_rules": "Nividous-LPA-Help/Working_with_Business_Rule/Working_with_Business_rules.htm",
    "cc_about": "CC-Help/About Nividous RPA/About_Control_Center.htm",
    "cc_platform": "CC-Help/About Nividous RPA/Overview.htm",
    "genai_template_creation": "CC-Help/Working_with_Smart_Bot/Data_Extraction/CV_Model_Extraction/GenAI_Based_Data_Extraction/GenAI_Template_Creation.htm",
    "maker_checker": "CC-Help/Working_with_Smart_Bot/Data_Extraction/Verifying_Extraction_using_MakerChecker_Screen.htm",
    "domain_template_creation": "CC-Help/Working_with_Smart_Bot/Data_Extraction/CV_Model_Extraction/Domain_Specific_Template_Creation.htm",
    "cloud_storage_cfg": "CC-Help/Working_with_Smart_Bot/Configurations/Cloud_Storage_Provider_Configuration.htm",
    "text_clustering": "CC-Help/Working_with_Smart_Bot/Working_with_Text_Clustering/Working_with_Text_Clustering.htm",
    "api_cc_v2": "API-Help/APIs_for_Control_Center_V2/APIs_for_Control_Center_V2.htm",
    "api_sb_v2": "API-Help/APIs_Smart_Bot_V2/APIs_for_Smart_Bot_V2.htm",
    "infra_home": "Infrastructure-Help/Infrastructure/Infrastructure.htm",
}


def to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr|/td)[^>]*>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in unescape(html).split("\n")]
    res, blank = [], False
    for l in lines:
        if not l:
            if not blank:
                res.append("")
            blank = True
        else:
            res.append(l)
            blank = False
    return "\n".join(res)


out = Path("pages")
out.mkdir(exist_ok=True)
for name, rel in TARGETS.items():
    r = s.get(ROOT + rel, timeout=90)
    if r.status_code != 200:
        print(f"{name}: HTTP {r.status_code}")
        continue
    txt = to_text(r.text)
    (out / f"{name}.txt").write_text(txt, encoding="utf-8")
    print(f"{name}: {len(txt)} chars")
