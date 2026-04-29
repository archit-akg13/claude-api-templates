"""Regex-first PDF field extractor used as a fast pre-step before Claude.

For structured documents (invoices, IDs, contracts) regex extraction handles
90% of fields in milliseconds. Only the ambiguous fields go to the model.
This script returns a dict of confidently-extracted fields and a list of
fields that need LLM extraction.

Usage:
    python regex_pdf_field_extractor.py path/to/doc.pdf
"""
import re
import sys
from pathlib import Path
from typing import Optional

import pdfplumber


FIELD_PATTERNS = {
      'gstin': re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b'),
      'pan': re.compile(r'\b[A-Z]{5}\d{4}[A-Z]\b'),
      'aadhaar_masked': re.compile(r'\bX{4}\s?X{4}\s?\d{4}\b'),
      'invoice_no': re.compile(
                r'(?:Invoice|Bill)\s*(?:No\.?|#)\s*[:\-]?\s*([A-Z0-9\-/]+)', re.I
            ),
      'date_dmy': re.compile(r'\b(\d{2}[\-/]\d{2}[\-/]\d{4})\b'),
      'amount_inr': re.compile(
                r'(?:Total|Grand\s*Total|Amount)[^\d]*(?:Rs\.?|INR)?\s*([\d,]+\.\d{0,2})',
                re.I,
            ),
      'email': re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
      'phone_in': re.compile(r'\b(?:\+91[\-\s]?)?[6-9]\d{9}\b'),
  }


def pdf_to_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return '\n'.join((p.extract_text() or '') for p in pdf.pages)


                         def extract_fields(text: str) -> dict:
                             """Run every pattern and return the first match for each field."""
                             out = {}
                             for name, pat in FIELD_PATTERNS.items():
                                 m = pat.search(text)
                                 if m:
                                     out[name] = m.group(1) if m.groups() else m.group(0)
                                           return out


                         def summarize(path: str) -> dict:
                             text = pdf_to_text(Path(path))
                             fields = extract_fields(text)
                             needs_llm = [k for k in FIELD_PATTERNS if k not in fields]
                                   return {
                                       'file': path,
                                       'extracted': fields,
                                       'needs_llm': needs_llm,
                                       'char_count': len(text),
                                   }


                                          if __name__ == '__main__':
                                              if len(sys.argv) < 2:
                                                  print('Usage: python regex_pdf_field_extractor.py <pdf>')
                                                  sys.exit(1)
                                              result = summarize(sys.argv[1])
                                              print('Extracted via regex:')
                                              for k, v in result['extracted'].items():
                                                  print(f'  {k:20s} {v}')
                                              if result['needs_llm']:
                                                  print('\nFields needing Claude (or other LLM) follow-up:')
                                                  for k in result['needs_llm']:
                                                      print(f'  - {k}')
                                          
