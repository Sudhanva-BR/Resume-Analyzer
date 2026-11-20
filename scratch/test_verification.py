import io
import openpyxl
from app import _detect_candidate_level, _compute_priority_and_fitment, _to_excel
from pdf_parser import _extract_teaching_experience, _find_all_usernames, _LC_PATTERNS

# 1. Unqualified Candidate Test
cand_unqual = {
    'name': 'Low Scorer',
    'url': 'https://example.com/low.pdf',
    'cf_stats': {'max_rating': 1350, 'contests_to_max': 4, 'total_contests': 10},
    'cc_stats': {'max_rating': 1500, 'contests_to_max': 5, 'total_contests': 12},
    'lc_stats': {'max_rating': 1700, 'contests_to_max': 8, 'total_contests': 15},
    'icpc_achievements': [{'text': 'ICPC regionalist in 2023'}],
    'teaching_experience': {'has_experience': True, 'duration_text': '2 years'},
    'graduation_year': 2024,
    'caught_count': 0,
    'caught_penalties': []
}
lvl = _detect_candidate_level(cand_unqual)
pf = _compute_priority_and_fitment(cand_unqual, 'Auto (Detect Level)')
assert lvl == 'not qualified', f"Expected not qualified, got {lvl}"
assert pf['level'] == 'not qualified', f"Expected not qualified, got {pf['level']}"
assert pf['priority'] == 'P3', f"Expected P3, got {pf['priority']}"
assert pf['fitment_score'] == 2, f"Expected 2, got {pf['fitment_score']}"
print("TEST 1 (Unqualified candidate): PASS")

# 2. L1 Candidate Test
cand_l1 = {
    'name': 'L1 Scorer',
    'url': 'https://example.com/l1.pdf',
    'cf_stats': {'max_rating': 1450, 'contests_to_max': 6, 'total_contests': 25},
    'cc_stats': {'max_rating': None, 'contests_to_max': None, 'total_contests': None},
    'lc_stats': {'max_rating': None, 'contests_to_max': None, 'total_contests': None},
    'icpc_achievements': [{'text': 'ICPC regionalist in 2023'}],
    'teaching_experience': {'has_experience': False, 'duration_text': None},
    'graduation_year': 2025,
    'caught_count': 0,
    'caught_penalties': []
}
lvl_l1 = _detect_candidate_level(cand_l1)
pf_l1 = _compute_priority_and_fitment(cand_l1, 'Auto (Detect Level)')
assert lvl_l1 == 'L1', f"Expected L1, got {lvl_l1}"
assert pf_l1['level'] == 'L1'
assert pf_l1['priority'] == 'P1'
assert pf_l1['fitment_score'] == 4  # 3 base + 1 ICPC = 4
print("TEST 2 (L1 Candidate): PASS")

# 3. Caught in 2 questions test
cand_caught = {
    'name': 'Caught Candidate',
    'url': 'https://example.com/caught.pdf',
    'cf_stats': {'max_rating': 1650, 'contests_to_max': 12, 'total_contests': 35},
    'cc_stats': {'max_rating': None, 'contests_to_max': None, 'total_contests': None},
    'lc_stats': {'max_rating': None, 'contests_to_max': None, 'total_contests': None},
    'icpc_achievements': [],
    'teaching_experience': {'has_experience': True, 'duration_text': '1 year'},
    'graduation_year': 2023,
    'caught_count': 2,
    'caught_penalties': ['Codeforces (2 questions skipped)']
}
pf_caught = _compute_priority_and_fitment(cand_caught, 'Auto (Detect Level)')
assert pf_caught['priority'] == 'P3', f"Expected P3, got {pf_caught['priority']}"
print("TEST 3 (Caught Candidate): PASS")

# 4. Excel generation test
cand_unqual['priority'] = pf['priority']
cand_unqual['level'] = pf['level']
cand_unqual['fitment_score'] = pf['fitment_score']

cand_caught['priority'] = pf_caught['priority']
cand_caught['level'] = pf_caught['level']
cand_caught['fitment_score'] = pf_caught['fitment_score']

excel_bytes = _to_excel([cand_unqual, cand_caught])
wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
ws = wb.active
cells_c = [ws.cell(row=r, column=3).value for r in range(2, ws.max_row + 1)]
# Check for caught row in cand_caught
assert any('Caught in 2 questions' in str(v) for v in cells_c), 'Expected Caught in 2 questions in context column'
print("TEST 4 (Excel generation): PASS")

# 5. Teaching Experience false positives test
t1 = _extract_teaching_experience("Member of Training and Placement Cell\nCoordinator of Placement Team")
assert t1['has_experience'] == False, f"Expected False, got {t1}"

t2 = _extract_teaching_experience("Built web portal for teachers and students with teacher dashboard")
assert t2['has_experience'] == False, f"Expected False, got {t2}"

t3 = _extract_teaching_experience("Model training on CNN with 95% accuracy using PyTorch")
assert t3['has_experience'] == False, f"Expected False, got {t3}"

t4 = _extract_teaching_experience("Teaching Assistant for DSA\nAug 2023 - Dec 2023")
assert t4['has_experience'] == True, f"Expected True, got {t4}"
assert "4 months" in t4['duration_text'], f"Expected 4 months, got {t4['duration_text']}"
print("TEST 5 (Teaching false positive filters): PASS")

# 6. Leetcode Solved handle test
corpus = "• LeetCode: Solved 600+ DSA problems\nLeetCode: https://leetcode.com/u/real_coder"
handles = _find_all_usernames(corpus, _LC_PATTERNS)
assert "solved" not in [h.lower() for h in handles], f"Solved should be ignored! got {handles}"
assert "600" not in handles, f"Numeric 600 should be ignored! got {handles}"
assert "real_coder" in handles, f"real_coder should be extracted! got {handles}"
print("TEST 6 (LeetCode handle extraction): PASS")

print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")
