# ruff: noqa: E501
"""Hawaii DOE statewide teacher salary schedule (D-031): text in ``pdftotext -layout`` form."""

from __future__ import annotations

import datetime as dt

from pay_pipeline.schedules import hi_doe
from pay_pipeline.schedules.state_import import STATE_KEY
from pay_pipeline.schedules.validate import validate

# Excerpt of "Teacher's Annual Rate Salary Schedule (10-Month)", SY2026-27 (HIDOE, Exhibit E).
PAGE = """\
                                                                                                EXHIBIT E
                                                                 TEACHER'S ANNUAL RATE SALARY SCHEDULE (10-MONTH)
                                                                        Effective the First Work Day of the 2026-2027 School Year
                                  CLASS II                  CLASS III                CLASS IV                  CLASS V                 CLASS VI                  CLASS VII               CLASS VIII
Initial Classification                 BA                 BA+30 or MA                                                                                            Doctorate
Reclassification                                       Class II + 15 credits    Class III + 15 credits   Class IV + 15 credits     Class V + 15 credits     Class VI + 15 credits   Class VII + 15 credits*
            14B5             T02-14B        78,720     T03-14B       85,018     T04-14B       88,418     T05-14B       91,955     T06-14B       95,633      T07-14B     101,371     T08-14B       105,426
            14A5             T02-14A        74,264     T03-14A       80,204     T04-14A       83,414     T05-14A       86,750     T06-14A       90,221      T07-14A       95,632    T08-14A        99,457
            14 5             T02-14         72,100     T03-14        77,868     T04-14        80,985     T05-14        84,223     T06-14        87,591      T07-14        92,849    T08-14         96,562
             55              T02-05         55,259     T03-05        59,680     T04-05        62,068     T05-05        64,549     T06-05        67,132      T07-05        71,160    T08-05         74,006
    (ENTRY LEVEL) 45         T02-04         53,649     T03-04        57,942     T04-04        60,260     T05-04        62,668     T06-04        65,177      T07-04        69,086    T08-04         71,850
"""


def test_reads_codes_not_margin() -> None:
    d = hi_doe.read_text(PAGE)
    assert d is not None
    assert (d.state, d.state_district_id, d.school_year) == ("HI", "001", "2026-27")
    assert [s.label_raw for s in d.steps] == [
        "Step 4 (entry level)",
        "Step 5",
        "Step 14",
        "Step 14A",
        "Step 14B",
    ]
    assert [ln.lane_normalized for ln in d.lanes][:2] == ["BA", None]
    assert len(d.lanes) == 7
    assert d.amount(0, 0) == 53_649_00
    assert d.amount(1, 0) == 55_259_00
    assert d.amount(4, 6) == 105_426_00
    assert validate(d, today=dt.date(2026, 11, 13)) == []


def test_missing_cell_is_not_guessed() -> None:
    assert hi_doe.read_text(PAGE.replace("T05-14A", "T05 14A")) is None


def test_other_page_is_ignored() -> None:
    assert hi_doe.read_text(PAGE.replace("(10-MONTH)", "(12-MONTH)")) is None


def test_state_key() -> None:
    assert STATE_KEY["HI"]("HI-001") == "001"
    assert STATE_KEY["HI"]("HI-1") is None
