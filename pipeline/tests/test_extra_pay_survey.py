"""Công đoạn 11: nhận diện trang phụ cấp HLV và trang lương dạy thay (dữ liệu giả lập)."""

from pay_pipeline.extra_pay import survey

STIPEND = """Test Unified School District — Extra Duty Stipend Schedule 2026-27
Football Head Varsity $6,084   Football Assistant $3,648
Basketball Head $4,936         Volleyball Head $3,313
Band Director $5,000           Drama $2,945
"""

TEACHER = """Teacher Salary Schedule 2026-27
Step BA MA
1 $48,000 $52,000
2 $49,100 $53,100
"""

SUB = """Substitute Teacher Pay Rates 2026-27
Daily rate, certificated substitute $175.00
Long-term substitute (11+ days) daily rate $225.00
"""


def test_stipend_page() -> None:
    assert survey.stipend_page(STIPEND) == 5
    assert survey.stipend_page(TEACHER) == 0  # lương năm, không có môn nào
    assert survey.stipend_page("Coach stipend: football $500") == 0  # quá ít số tiền


def test_substitute_page() -> None:
    assert survey.substitute_page(SUB)
    assert not survey.substitute_page(TEACHER)
    assert not survey.substitute_page("Substitute daily rate: see HR")  # không có số tiền


def test_amounts_need_money_format() -> None:
    assert survey.amounts("$4,300 and 950 and 2,700.00 and $85") == [4300, 2700, 85]


def test_survey_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    html = tmp_path / "9999999-abc.html"
    rows = "".join(f"<tr><td>{line}</td></tr>" for line in (STIPEND + SUB).splitlines())
    html.write_text(f"<html><body><table>{rows}</table></body></html>")
    r = survey.survey_file(html, "https://example.invalid/x.html", "0" * 64)
    assert r is not None and r.nces_id == "9999999"
    assert r.stipend_pages == [1] and r.substitute_pages == [1]
    assert survey.survey_file(tmp_path / "x.txt") is None
