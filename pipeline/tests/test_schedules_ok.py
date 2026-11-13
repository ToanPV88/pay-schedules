# ruff: noqa: E501
"""Oklahoma state book of local salary schedules (D-029): text in ``pdftotext -layout`` form."""

from __future__ import annotations

from pay_pipeline.schedules import ok_sde

# Excerpts of "Oklahoma Public Schools Local Salary Schedules 2025-2026" (OSDE), pages 355, 5, 7.
TULSA = """\
                                                                   OKLAHOMA STATE DEPARTMENT OF EDUCATION
                                                                        Office of School Personnel Records
                                                                              School Year: 2025-2026
COUNTY-DISTRICT NAME: TULSA- TULSA                  COUNTY-DISTRICT CODE: 72 - I001                                                                             Hours/Days: 7.84/176
  Years      Bach.    *Bach.+     *Bach.+    *Bach.+    NBCT      *NBCT    *NBCT    *NBCT     Mast.   *Mast.+   *Mast.+   *Mast.+   NBCT     *NBCT    *NBCT    *NBCT     Doct.   *NBCT
 of Exp.    Degree     0 Hrs       0 Hrs      0 Hrs      Bach.    Bach.+   Bach.+   Bach.+   Degree    30 Hrs    60 Hrs    0 Hrs     Mast.   Mast.+   Mast.+   Mast.+   Degree    Doct.
                                                        Degree     0 Hrs    0 Hrs    0 Hrs                                          Degree   30 Hrs   60 Hrs    0 Hrs            Degree
    0        43,500                                      44,658                              44,775   46,050    47,325              45,933   47,208   48,483            48,600   49,758
    1        44,153                                      45,328                              45,447   46,741    48,035              46,622   47,916   49,210            49,329   50,504
    2        44,815                                      46,008                              46,128   47,442    48,755              47,321   48,635   49,948            50,069   51,262
    3        45,487                                      46,698                              46,820   48,153    49,487              48,031   49,364   50,698            50,820   52,031
    4        46,169                                      47,398                              47,523   48,876    50,229              48,752   50,105   51,458            51,582   52,811
"""

MINIMUM = """\
                                                     Lindel Fields
                                       State Superintendent of Public Instruction
                       Oklahoma State Department of Education, Office of School Personnel Records
                               2025-2026 STATE MINIMUM TEACHER SALARY SCHEDULE
                                                          70 O.S. § 18-114.15

Beginning with the 2025-2026 school year, certified personnel, as defined in 70 O.S. § 26-103, in the public schools of Oklahoma
shall receive in salary and/or fringe benefits not less than the amount specified in the following schedule. When determining
minimum salary, "fringe benefits" shall mean only the employee's share of retirement, if paid by the district.


                                                  *Bachelor's +                                  *Master's +
       Year of                Bachelor's         National Board             Master's            National Board              Doctor's
       Experience              Degree             Certification             Degree               Certification              Degree
            0                  $39,601               $40,759                 $40,991                 $42,149                $42,381
             1                 $40,035               $41,193                 $41,425                 $42,583                $42,815
             2                 $40,469               $41,628                 $41,859                 $43,018                $43,249
             3                 $40,904               $42,062                 $42,294                 $43,452                $43,684
             4                 $41,338               $42,496                 $42,728                 $43,886                $44,118
             5                 $42,810               $43,968                 $44,200                 $45,358                $45,590
             6                 $43,273               $44,432                 $44,663                 $45,822                $46,054
             7                 $43,737               $44,895                 $45,127                 $46,285                $46,517
"""

LISTED = """\
                           THE FOLLOWING SCHOOL DISTRICTS ARE USING
                         THE STATE MINUMUM SALARY SCHEDULE IN 2025-2026:


ADAIR COUNTY                                  CRAIG COUNTY                                   JACKSON COUNTY
01C019 PEAVINE                                18C001 WHITE OAK                               33I001 NAVAJO
01I025 STILWELL
01I030 CAVE SPRINGS                           CREEK COUNTY                                   JEFFERSON COUNTY
                                              19I017 OLIVE                                   34I014 RINGLING
ALFALFA COUNTY
                                              19I020 OILTON
02I001 BURLINGTON
"""


def test_district_page() -> None:
    d = ok_sde.read_district_page(TULSA, 355, "2025-26")
    assert d is not None
    assert (d.state_district_id, d.district_name, d.contract_days) == (
        "72I001",
        "TULSA- TULSA",
        176,
    )
    assert [ln.label_raw for ln in d.lanes] == [
        "Bach. Degree",
        "NBCT Bach. Degree",
        "Mast. Degree",
        "Mast.+ 30 Hrs",
        "Mast.+ 60 Hrs",
        "NBCT Mast. Degree",
        "NBCT Mast.+ 30 Hrs",
        "NBCT Mast.+ 60 Hrs",
        "Doct. Degree",
        "NBCT Doct. Degree",
    ]
    assert [ln.lane_normalized for ln in d.lanes][:5] == ["BA", None, "MA", "MA+30", "MA+60"]
    assert [s.label_raw for s in d.steps][:3] == ["0", "1", "2"]
    assert d.amount(0, 0) == 4_350_000 and d.amount(0, 9) == 4_975_800
    assert d.source_page == 355


def test_layout_not_understood_is_rejected() -> None:
    shifted = TULSA.replace("    0        43,500", "    0           43,500", 1)
    assert ok_sde.read_district_page(shifted, 355, "2025-26") is None
    assert ok_sde.read_district_page("School Year: 2025-2026", 1, "2025-26") is None


def test_state_minimum_and_listed_districts() -> None:
    m = ok_sde.read_minimum(MINIMUM, 5, "2025-26")
    assert m is not None
    assert [ln.lane_normalized for ln in m.lanes] == ["BA", None, "MA", None, "PhD"]
    assert m.amount(0, 0) == 3_960_100 and m.amount(1, 4) == 4_281_500
    listed = ok_sde.listed_on_minimum(LISTED)
    assert ("33I001", "NAVAJO") in listed and ("01I025", "STILWELL") in listed
    assert ("19I020", "OILTON") in listed
    assert ok_sde.school_year(TULSA) == "2025-26"
