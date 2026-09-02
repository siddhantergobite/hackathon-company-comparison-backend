"""Fetch specific Nividous help topics and dump them as readable text."""
import re
import sys
from html import unescape
from pathlib import Path

import requests

ROOT = "https://community.nividous.com/help-documents/"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"

TARGETS = {
    "rpa_libraries": "Nividous-RPA-Help/Lib_Documentation/RPA_Libraries_Documentation.htm",
    "rpa_genai": "Nividous-RPA-Help/About RPA Studio/Generating_RPA_Code_through_GenAI.htm",
    "rpa_about_platform": "Nividous-RPA-Help/About Nividous RPA/About Nividous RPA.htm",
    "pretrained_text_clf": "CC-Help/Working_with_Smart_Bot/Classification/Text_Classification/Pretrained_Text_Classifier_Models.htm",
    "pretrained_nlp_ext": "CC-Help/Working_with_Smart_Bot/Data_Extraction/CV_Model_Extraction/NLP_Model_Extraction/Pretrained_NLP_Extraction_Models.htm",
    "pretrained_predictive": "CC-Help/Working_with_Smart_Bot/Predictive_Analysis/PreTrained_Predictive_Analysis_Models.htm",
    "ootb_domain": "CC-Help/Working_with_Smart_Bot/Data_Extraction/CV_Model_Extraction/Out_of_the_Box_(Domain).htm",
    "genai_usecases": "CC-Help/Working_with_Smart_Bot/Other_Use_Cases_of_Generative_AI/Other_Use_Cases_of_Generative_AI.htm",
    "genai_extraction_vlm": "CC-Help/Working_with_Smart_Bot/Data_Extraction/CV_Model_Extraction/GenAI_Based_Data_Extraction/GenAI_Based_Data_Extraction.htm",
    "doc_processor": "CC-Help/Working_with_Document_Processor/Working_with_Document_Processor.htm",
    "doc_proc_steps": "CC-Help/Working_with_Document_Processor/Creating_New_Configuration/Adding_Steps/Adding_Steps.htm",
    "brms": "CC-Help/Working_with_BRMS/Working_with_BRMS.htm",
    "smartbot_about": "CC-Help/Working_with_Smart_Bot/Working_with_Smart_Bot.htm",
    "ocr_engine_config": "CC-Help/Working_with_Smart_Bot/Configurations/OCR_Engine_Configuration.htm",
    "infra": "Infrastructure-Help/home.htm",
}


def to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr|/td)[^>]*>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    text = unescape(html)
    lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in text.split("\n")]
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
sys.stdout.flush()
