"""Connecticut (CEA book) and West Virginia (WVDE book) readers (D-071)."""

from __future__ import annotations

from pay_pipeline.schedules import ct_cea, wv_wvde

CT_PAGE = """\
2025‐2026 SALARY SCHEDULES
FAIRFIELD COUNTY

BETHEL                 STEP     BA       BA+15      BA+30       MA
                         1    $54,501   $55,001    $56,818    $59,154
                         2    $55,435   $55,935    $58,449    $60,793
                         3    $56,385   $56,885    $60,127    $62,481
                        14                         $82,094    $84,416

RIDGEFIELD   STEP     BA        BA 18     BA 30/ MA
                                                       YR 9
              2     $51,961    $56,118    $58,715     $61,834
              3     $54,010    $58,329    $61,030     $64,270
              4     $56,054    $60,537    $63,341     $66,705

                                                              2 of 121
"""


def test_ct_grids_and_blank_cells() -> None:
    bethel, ridgefield = ct_cea.read_pages([CT_PAGE])
    assert bethel.state_district_id == "BETHEL"
    assert bethel.school_year == "2025-26"
    assert [ln.label_raw for ln in bethel.lanes] == ["BA", "BA+15", "BA+30", "MA"]
    assert [bethel.amount(3, k) for k in range(4)] == [None, None, 8209400, 8441600]
    assert bethel.cells[(3, 0)].note == ct_cea.BLANK
    # A heading over two lines: the second line names the last column.
    assert [ln.label_raw for ln in ridgefield.lanes] == ["BA", "BA 18", "BA 30/ MA", "YR 9"]
    assert ridgefield.amount(0, 3) == 6183400


def test_ct_district_key() -> None:
    assert ct_cea.district_key("Regional School District 09") == "REGION 9"
    assert ct_cea.district_key("REGION 09") == "REGION 9"
    assert ct_cea.district_key("East Hampton School District") == "EAST HAMPTON"
    assert ct_cea.district_key("AMITY") == "REGION 5"
    assert ct_cea.district_key("Regional School District 05") == "REGION 5"


def _wv_page(cls: str, base: int) -> str:
    supp = "      1,781        -         1,781       -  "
    rows = "\n".join(
        f" {y:<6}{base + 300 * y:>9,}{supp}{base + 300 * y + 1781:>9,}" for y in range(12)
    )
    return f"""\
                  BARBOUR COUNTY BOARD OF EDUCATION
                   TEACHERS ANNUAL SALARY SCHEDULE
                         FOR THE 2025-26 YEAR

                               {cls}

Years   State        State      1984 Co    SS Col 5   County   Total
 Exp    Basic        Suppl       Suppl     St Suppl   Suppl    Salary

{rows}
                                   -1-
"""


def test_wv_county_total_salary() -> None:
    pages = [_wv_page("A.B.", 39000), _wv_page("M.A.", 42000), "TEACHERS' STATE MINIMUM"]
    (d,) = wv_wvde.read_pages(pages)
    assert d.state_district_id == "BARBOUR"
    assert d.school_year == "2025-26"
    assert [(ln.label_raw, ln.lane_normalized) for ln in d.lanes] == [
        ("A.B. (Bachelor's)", "BA"),
        ("M.A. (Master's)", "MA"),
    ]
    assert len(d.steps) == 12 and d.steps[0].label_raw == "0 years"
    assert d.amount(0, 0) == 4078100 and d.amount(11, 1) == 4708100
    assert wv_wvde.district_key("Barbour County Schools") == "BARBOUR"
