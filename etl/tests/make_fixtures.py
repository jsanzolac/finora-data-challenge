"""Writes etl/tests/fixtures/dirty/*.csv: small files with one planted fault each.
Run once; the files are committed as fixtures. BOM + CRLF + no final newline,
like the real files."""

from pathlib import Path

D = Path(__file__).resolve().parent / "fixtures" / "dirty"
BOM = b"\xef\xbb\xbf"
ENDS = ["1/31/2022", "2/28/2022", "3/31/2022", "4/30/2022", "5/31/2022", "6/30/2022"]


def tx(rows):
    return BOM + b"\r\n".join([b"ID,month,amount"] + rows)


def base_tx():
    amounts = {1: ["5", "5", "5", "5", "5", "5"], 2: ["0", "3", "3", "0", "3", "3"], 3: ["2", "2", "2", "2", "2", "2"]}
    return [f"{c},{m},{a}".encode() for c, amts in amounts.items() for m, a in zip(ENDS, amts)]


def ind(rows=None):
    rows = rows or [b"Cliente 1,Retail", b"Cliente 2,Salud", b"Cliente 3,Restaurantes"]
    return BOM + b"\r\n".join([b"ID,Industria"] + rows)


SMH = b"Month,PaidMedia,Travel,PublicidadNoWeb,Freelance,SoftwareTools,Team,PayrollExpenses"


def sm(rows=None):
    rows = rows or [f"2022-0{i},$0.001,$0.001,$0.001,$0.001,$0.001,$0.001,$0.001".encode() for i in range(1, 7)]
    return BOM + b"\r\n".join([SMH] + rows)


def replace(rows, idx, new):
    rows = list(rows)
    rows[idx] = new
    return rows


def month_ends(n, y=2022, m=1):
    import calendar
    out = []
    for _ in range(n):
        out.append(f"{m}/{calendar.monthrange(y, m)[1]}/{y}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def uneven_split_tx():
    """SB-11 cases F1-F18 of cdo_uneven_split.md § 11, one customer per case
    (customer 100 + N is case FN), on an 18-month W (2022-01 -> 2023-06) so a
    pair can have 14+ months after it (F16). Raw strings are kept as written."""
    n = 18
    ends = month_ends(n)

    def cust(head, fill, tail=()):
        return list(head) + [fill] * (n - len(head) - len(tail)) + list(tail)

    cases = {
        101: cust(["6.72", "6.72", "7.154784", "6.285216", "6.72"], "6.72"),       # F1 customer 12 pattern
        102: cust(["9.45", "1.05", "17.85", "9.45"], "9.45"),                      # F2 first month below b
        103: cust(["6.72", "7.154784", "6.285217", "6.72"], "6.72"),               # F3 sum off by 0.000001
        104: cust(["6.72", "7.05012", "6.80988", "6.93"], "6.93"),                 # F4 baselines differ
        105: cust(["15.12", "12.6", "17.64", "0"], "15.12", ["12.6", "17.64"]),    # F5 m+2 unpaid; pair at W end
        106: cust(["0", "6.72", "7.0", "6.44", "6.72"], "6.72"),                   # F6 m-1 is the first paid month
        107: cust(["6.72", "7.154784", "6.285216", "bad", "6.72"], "6.72"),        # F7 hole (excluded) at m+2
        108: cust(["6.72", "bad", "7.154784", "6.285216", "6.72"], "6.72"),        # F8 hole (excluded) at m-1
        109: cust(["6", "0", "12", "14", "10", "12"], "12"),                       # F9 baseline is an arrears q
        110: cust(["9.45", "1.05", "17.85", "9.45", "3.15", "15.75", "9.45"], "9.45"),  # F10 shared baseline
        111: cust(["9.45", "9.45", "3.15", "15.75", "3.15", "15.75", "9.45"], "9.45"),  # F11 back-to-back
        112: cust(["5.093298", "5.093298", "5.342904", "5.218101"], "5.218101"),   # F12 price step billed late
        113: cust(["24.6036", "24.1164", "24.1164", "24.6036"], "24.6036"),        # F13 two-month dip
        114: cust(["6.72", "14.5", "-1.06", "6.72"], "6.72"),                      # F14 negative in the window
        115: cust(["3.15", "4.2", "2.1", "3.15"], "3.15"),                         # F15 left-censored, pair W[1]
        116: cust(["5.25", "6.3", "4.2", "5.25"], "5.25"),                         # F16 14+ months after
        117: cust(["6.72", "7.154784", "6.285216", "6.720000"], "6.72"),           # F17 6.72 vs 6.720000
        118: cust(["400", "560", "240", "400"], "400"),                            # F18 outlier with a pair
    }
    return tx([f"{c},{m},{a}".encode() for c, amts in cases.items() for m, a in zip(ends, amts)])


FIXTURES = {
    "clean_transactions.csv": tx(base_tx()),
    "clean_industry.csv": ind(),
    "clean_sm_spend.csv": sm(),
    "tx_bad_month.csv": tx(replace(base_tx(), 0, b"1,01/31/2022,5")),
    "tx_non_numeric.csv": tx(replace(base_tx(), 1, b"1,2/28/2022,1e3")),
    "tx_seventh_decimal.csv": tx(replace(base_tx(), 2, b"1,3/31/2022,5.1234567")),
    "tx_duplicate_key.csv": tx(base_tx() + [b"1,6/30/2022,5"]),
    "tx_bad_id.csv": tx(replace(base_tx(), 6, b"02,1/31/2022,0")),
    "tx_missing_month.csv": tx(base_tx()[:3] + base_tx()[4:]),
    "tx_wrong_field_count.csv": tx(replace(base_tx(), 3, b"1,4/30/2022,5,extra")),
    "tx_undecodable.csv": tx(replace(base_tx(), 4, b"1,5/31/2022,5\xff")),
    "tx_control_char.csv": tx(replace(base_tx(), 4, b"1,5/31/2022,\t5")),
    "tx_not_month_end.csv": tx(replace(base_tx(), 4, b"1,5/30/2022,5")),
    "tx_negative_amount.csv": tx(replace(base_tx(), 5, b"1,6/30/2022,-2.5")),
    # hole fixtures (approved_data_rules.md § Expected results, "Hole fixtures")
    "tx_hole_bad_amount_in_gap.csv": tx(replace(replace(replace(base_tx(), 7, b"2,2/28/2022,3"), 9,
                                                        b"2,4/30/2022,x"), 8, b"2,3/31/2022,0")),
    "tx_hole_before_first_paid.csv": tx(replace(base_tx(), 6, b"2,1/31/2022,bad")),
    "tx_hole_p_minus_1.csv": tx([b"4,1/31/2022,5", b"4,2/28/2022,?", b"4,3/31/2022,5", b"4,4/30/2022,0",
                                 b"4,5/31/2022,7", b"4,6/30/2022,5"] + base_tx()),
    "tx_hole_last_month.csv": tx(replace(base_tx(), 17, b"3,6/30/2022,")),
    # SB-11 uneven split (cdo_uneven_split.md § 11, fixtures F1-F18)
    "tx_uneven_split.csv": uneven_split_tx(),
    "ind_empty_record.csv": ind() + b"\r\n,",
    "ind_unmapped.csv": ind([b"Cliente 1,Retail", b"Cliente 2,Miner\xc3\xada", b"Cliente 3,Restaurantes"]),
    "ind_bad_id.csv": ind([b"Cliente 1,Retail", b"Cliente 02,Salud", b"Cliente 3,Restaurantes"]),
    "ind_duplicate.csv": ind([b"Cliente 1,Retail", b"Cliente 2,Salud", b"Cliente 3,Restaurantes",
                              b"Cliente 1,Retail"]),
    "sm_bad_cell.csv": sm(None)[:0] or sm([f"2022-0{i},$0.001,$0.001,$0.001,$0.001,$0.001,$0.001,"
                                            f"{'$0.01' if i == 3 else '$0.001'}".encode() for i in range(1, 7)]),
    "sm_bad_month.csv": sm([f"2022-{'13' if i == 6 else '0' + str(i)},$0.100,$0.010,$0.020,$0.030,$0.040,"
                            f"$0.001,$0.001".encode() for i in range(1, 7)]),
    "sm_month_gap.csv": sm([f"2022-0{i},$0.001,$0.001,$0.001,$0.001,$0.001,$0.001,$0.001".encode()
                            for i in (1, 2, 4, 5, 6)]),
    "sm_negative_other.csv": sm([f"2022-0{i},{'-$0.001' if i == 2 else '$0.001'},$0.001,$0.001,$0.001,"
                                 f"$0.001,$0.001,$0.001".encode() for i in range(1, 7)]),
}

if __name__ == "__main__":
    D.mkdir(parents=True, exist_ok=True)
    for name, data in FIXTURES.items():
        (D / name).write_bytes(data)
    print(f"wrote {len(FIXTURES)} fixtures")
