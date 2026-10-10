"""Extractor for Lucky Star: Net Idol Meister (PSP, ULJM05542).

Unpacks sc.cpk, vo.cpk, union.cpk, lt.bin and pr.bin of PSP_GAME/USRDIR/DATA: one folder
per data file, then per file type, then per category. Output names are ASCII (romaji).
See README.md for the output layout, the formats and the names.

    python3 lsnim_extract.py DATA_folder [output_folder]
"""
