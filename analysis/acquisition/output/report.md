# Acquisition funnel and new-customer signals

Source: silver layer built from `data/` with the Glue ETL engine; months 2022-01 to 2024-10. Won excludes the 377 customers whose first payment is in 2022-01. Money in full units (revenue x 10,000, spend x 100,000,000); currency not stated.

## Conversion rates (edit `RATES` at the top of the script)

| From stage | To stage | Conversion rate |
|---|---|---|
| New | Working | 0.80 |
| Working | Engaged | 0.40 |
| Engaged | SQL | 0.50 |
| SQL | Demo | 0.70 |
| Demo | Proposal | 0.60 |
| Proposal | Won | 0.40 |

Overall New → Won: 2.688%

## 1. Funnel built backwards from Won

### Full period (2022-02 to 2024-10, 33 months)

Won 1,584 (real); total S&M spend 7,581,800,000 (real).

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 58,928.6 | 128,661 | Estimated |
| Working | 47,142.9 | 160,826 | Estimated |
| Engaged | 18,857.1 | 402,065 | Estimated |
| SQL | 9,428.6 | 804,130 | Estimated |
| Demo | 6,600.0 | 1,148,758 | Estimated |
| Proposal | 3,960.0 | 1,914,596 | Estimated |
| Won | 1,584.0 | 4,786,490 | Real |

### Arithmetic for 2024-10

1. **Won** = customers whose first payment above 0 is in 2024-10 = **50** (real).
2. **Total S&M spend** 2024-10 = PaidMedia 78,000,000 + Travel 12,000,000 + PublicidadNoWeb 26,000,000 + Freelance 0 + SoftwareTools 8,000,000 + Team 45,300,000 + PayrollExpenses 30,700,000 = **200,000,000** (real).
3. **Proposal** = Won ÷ 0.40 = 50.000 ÷ 0.40 = **125.000** (estimated).
4. **Demo** = Proposal ÷ 0.60 = 125.000 ÷ 0.60 = **208.333** (estimated).
5. **SQL** = Demo ÷ 0.70 = 208.333 ÷ 0.70 = **297.619** (estimated).
6. **Engaged** = SQL ÷ 0.50 = 297.619 ÷ 0.50 = **595.238** (estimated).
7. **Working** = Engaged ÷ 0.40 = 595.238 ÷ 0.40 = **1488.095** (estimated).
8. **New** = Working ÷ 0.80 = 1488.095 ÷ 0.80 = **1860.119** (estimated).
9. **Cost per unit** = total spend ÷ count at the stage, e.g. cost per Won = 200,000,000 ÷ 50 = **4,000,000**; cost per New = 200,000,000 ÷ 1860.119 = **107,520**.

### One table per month

#### 2022-02  (Won 108, spend 230,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 4,017.9 | 57,244 | Estimated |
| Working | 3,214.3 | 71,556 | Estimated |
| Engaged | 1,285.7 | 178,889 | Estimated |
| SQL | 642.9 | 357,778 | Estimated |
| Demo | 450.0 | 511,111 | Estimated |
| Proposal | 270.0 | 851,852 | Estimated |
| Won | 108.0 | 2,129,630 | Real |

#### 2022-03  (Won 30, spend 230,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,116.1 | 206,080 | Estimated |
| Working | 892.9 | 257,600 | Estimated |
| Engaged | 357.1 | 644,000 | Estimated |
| SQL | 178.6 | 1,288,000 | Estimated |
| Demo | 125.0 | 1,840,000 | Estimated |
| Proposal | 75.0 | 3,066,667 | Estimated |
| Won | 30.0 | 7,666,667 | Real |

#### 2022-04  (Won 19, spend 235,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 706.8 | 332,605 | Estimated |
| Working | 565.5 | 415,756 | Estimated |
| Engaged | 226.2 | 1,039,389 | Estimated |
| SQL | 113.1 | 2,078,779 | Estimated |
| Demo | 79.2 | 2,969,684 | Estimated |
| Proposal | 47.5 | 4,949,474 | Estimated |
| Won | 19.0 | 12,373,684 | Real |

#### 2022-05  (Won 38, spend 270,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,413.7 | 190,989 | Estimated |
| Working | 1,131.0 | 238,737 | Estimated |
| Engaged | 452.4 | 596,842 | Estimated |
| SQL | 226.2 | 1,193,684 | Estimated |
| Demo | 158.3 | 1,705,263 | Estimated |
| Proposal | 95.0 | 2,842,105 | Estimated |
| Won | 38.0 | 7,105,263 | Real |

#### 2022-06  (Won 33, spend 235,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,227.7 | 191,500 | Estimated |
| Working | 982.1 | 239,375 | Estimated |
| Engaged | 392.9 | 598,436 | Estimated |
| SQL | 196.4 | 1,196,873 | Estimated |
| Demo | 137.5 | 1,709,818 | Estimated |
| Proposal | 82.5 | 2,849,697 | Estimated |
| Won | 33.0 | 7,124,242 | Real |

#### 2022-07  (Won 32, spend 220,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,190.5 | 184,800 | Estimated |
| Working | 952.4 | 231,000 | Estimated |
| Engaged | 381.0 | 577,500 | Estimated |
| SQL | 190.5 | 1,155,000 | Estimated |
| Demo | 133.3 | 1,650,000 | Estimated |
| Proposal | 80.0 | 2,750,000 | Estimated |
| Won | 32.0 | 6,875,000 | Real |

#### 2022-08  (Won 26, spend 325,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 967.3 | 336,103 | Estimated |
| Working | 773.8 | 420,129 | Estimated |
| Engaged | 309.5 | 1,050,323 | Estimated |
| SQL | 154.8 | 2,100,646 | Estimated |
| Demo | 108.3 | 3,000,923 | Estimated |
| Proposal | 65.0 | 5,001,538 | Estimated |
| Won | 26.0 | 12,503,846 | Real |

#### 2022-09  (Won 17, spend 350,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 632.4 | 553,412 | Estimated |
| Working | 506.0 | 691,765 | Estimated |
| Engaged | 202.4 | 1,729,412 | Estimated |
| SQL | 101.2 | 3,458,824 | Estimated |
| Demo | 70.8 | 4,941,176 | Estimated |
| Proposal | 42.5 | 8,235,294 | Estimated |
| Won | 17.0 | 20,588,235 | Real |

#### 2022-10  (Won 32, spend 375,200,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,190.5 | 315,168 | Estimated |
| Working | 952.4 | 393,960 | Estimated |
| Engaged | 381.0 | 984,900 | Estimated |
| SQL | 190.5 | 1,969,800 | Estimated |
| Demo | 133.3 | 2,814,000 | Estimated |
| Proposal | 80.0 | 4,690,000 | Estimated |
| Won | 32.0 | 11,725,000 | Real |

#### 2022-11  (Won 19, spend 300,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 706.8 | 424,421 | Estimated |
| Working | 565.5 | 530,526 | Estimated |
| Engaged | 226.2 | 1,326,316 | Estimated |
| SQL | 113.1 | 2,652,632 | Estimated |
| Demo | 79.2 | 3,789,474 | Estimated |
| Proposal | 47.5 | 6,315,789 | Estimated |
| Won | 19.0 | 15,789,474 | Real |

#### 2022-12  (Won 26, spend 325,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 967.3 | 336,103 | Estimated |
| Working | 773.8 | 420,129 | Estimated |
| Engaged | 309.5 | 1,050,323 | Estimated |
| SQL | 154.8 | 2,100,646 | Estimated |
| Demo | 108.3 | 3,000,923 | Estimated |
| Proposal | 65.0 | 5,001,538 | Estimated |
| Won | 26.0 | 12,503,846 | Real |

#### 2023-01  (Won 60, spend 325,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,232.1 | 145,645 | Estimated |
| Working | 1,785.7 | 182,056 | Estimated |
| Engaged | 714.3 | 455,140 | Estimated |
| SQL | 357.1 | 910,280 | Estimated |
| Demo | 250.0 | 1,300,400 | Estimated |
| Proposal | 150.0 | 2,167,333 | Estimated |
| Won | 60.0 | 5,418,333 | Real |

#### 2023-02  (Won 30, spend 250,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,116.1 | 224,000 | Estimated |
| Working | 892.9 | 280,000 | Estimated |
| Engaged | 357.1 | 700,000 | Estimated |
| SQL | 178.6 | 1,400,000 | Estimated |
| Demo | 125.0 | 2,000,000 | Estimated |
| Proposal | 75.0 | 3,333,333 | Estimated |
| Won | 30.0 | 8,333,333 | Real |

#### 2023-03  (Won 38, spend 290,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,413.7 | 205,137 | Estimated |
| Working | 1,131.0 | 256,421 | Estimated |
| Engaged | 452.4 | 641,053 | Estimated |
| SQL | 226.2 | 1,282,105 | Estimated |
| Demo | 158.3 | 1,831,579 | Estimated |
| Proposal | 95.0 | 3,052,632 | Estimated |
| Won | 38.0 | 7,631,579 | Real |

#### 2023-04  (Won 51, spend 295,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,897.3 | 155,535 | Estimated |
| Working | 1,517.9 | 194,419 | Estimated |
| Engaged | 607.1 | 486,047 | Estimated |
| SQL | 303.6 | 972,094 | Estimated |
| Demo | 212.5 | 1,388,706 | Estimated |
| Proposal | 127.5 | 2,314,510 | Estimated |
| Won | 51.0 | 5,786,275 | Real |

#### 2023-05  (Won 47, spend 345,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,748.5 | 197,368 | Estimated |
| Working | 1,398.8 | 246,710 | Estimated |
| Engaged | 559.5 | 616,774 | Estimated |
| SQL | 279.8 | 1,233,549 | Estimated |
| Demo | 195.8 | 1,762,213 | Estimated |
| Proposal | 117.5 | 2,937,021 | Estimated |
| Won | 47.0 | 7,342,553 | Real |

#### 2023-06  (Won 46, spend 180,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,711.3 | 105,183 | Estimated |
| Working | 1,369.0 | 131,478 | Estimated |
| Engaged | 547.6 | 328,696 | Estimated |
| SQL | 273.8 | 657,391 | Estimated |
| Demo | 191.7 | 939,130 | Estimated |
| Proposal | 115.0 | 1,565,217 | Estimated |
| Won | 46.0 | 3,913,043 | Real |

#### 2023-07  (Won 65, spend 175,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,418.2 | 72,411 | Estimated |
| Working | 1,934.5 | 90,513 | Estimated |
| Engaged | 773.8 | 226,283 | Estimated |
| SQL | 386.9 | 452,566 | Estimated |
| Demo | 270.8 | 646,523 | Estimated |
| Proposal | 162.5 | 1,077,538 | Estimated |
| Won | 65.0 | 2,693,846 | Real |

#### 2023-08  (Won 66, spend 110,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,455.4 | 44,800 | Estimated |
| Working | 1,964.3 | 56,000 | Estimated |
| Engaged | 785.7 | 140,000 | Estimated |
| SQL | 392.9 | 280,000 | Estimated |
| Demo | 275.0 | 400,000 | Estimated |
| Proposal | 165.0 | 666,667 | Estimated |
| Won | 66.0 | 1,666,667 | Real |

#### 2023-09  (Won 56, spend 125,200,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,083.3 | 60,096 | Estimated |
| Working | 1,666.7 | 75,120 | Estimated |
| Engaged | 666.7 | 187,800 | Estimated |
| SQL | 333.3 | 375,600 | Estimated |
| Demo | 233.3 | 536,571 | Estimated |
| Proposal | 140.0 | 894,286 | Estimated |
| Won | 56.0 | 2,235,714 | Real |

#### 2023-10  (Won 64, spend 135,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,381.0 | 56,742 | Estimated |
| Working | 1,904.8 | 70,927 | Estimated |
| Engaged | 761.9 | 177,319 | Estimated |
| SQL | 381.0 | 354,638 | Estimated |
| Demo | 266.7 | 506,625 | Estimated |
| Proposal | 160.0 | 844,375 | Estimated |
| Won | 64.0 | 2,110,938 | Real |

#### 2023-11  (Won 72, spend 130,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,678.6 | 48,533 | Estimated |
| Working | 2,142.9 | 60,667 | Estimated |
| Engaged | 857.1 | 151,667 | Estimated |
| SQL | 428.6 | 303,333 | Estimated |
| Demo | 300.0 | 433,333 | Estimated |
| Proposal | 180.0 | 722,222 | Estimated |
| Won | 72.0 | 1,805,556 | Real |

#### 2023-12  (Won 55, spend 150,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,046.1 | 73,309 | Estimated |
| Working | 1,636.9 | 91,636 | Estimated |
| Engaged | 654.8 | 229,091 | Estimated |
| SQL | 327.4 | 458,182 | Estimated |
| Demo | 229.2 | 654,545 | Estimated |
| Proposal | 137.5 | 1,090,909 | Estimated |
| Won | 55.0 | 2,727,273 | Real |

#### 2024-01  (Won 57, spend 185,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,120.5 | 87,289 | Estimated |
| Working | 1,696.4 | 109,112 | Estimated |
| Engaged | 678.6 | 272,779 | Estimated |
| SQL | 339.3 | 545,558 | Estimated |
| Demo | 237.5 | 779,368 | Estimated |
| Proposal | 142.5 | 1,298,947 | Estimated |
| Won | 57.0 | 3,247,368 | Real |

#### 2024-02  (Won 32, spend 200,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,190.5 | 168,000 | Estimated |
| Working | 952.4 | 210,000 | Estimated |
| Engaged | 381.0 | 525,000 | Estimated |
| SQL | 190.5 | 1,050,000 | Estimated |
| Demo | 133.3 | 1,500,000 | Estimated |
| Proposal | 80.0 | 2,500,000 | Estimated |
| Won | 32.0 | 6,250,000 | Real |

#### 2024-03  (Won 43, spend 175,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,599.7 | 109,458 | Estimated |
| Working | 1,279.8 | 136,822 | Estimated |
| Engaged | 511.9 | 342,056 | Estimated |
| SQL | 256.0 | 684,112 | Estimated |
| Demo | 179.2 | 977,302 | Estimated |
| Proposal | 107.5 | 1,628,837 | Estimated |
| Won | 43.0 | 4,072,093 | Real |

#### 2024-04  (Won 69, spend 225,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,567.0 | 87,691 | Estimated |
| Working | 2,053.6 | 109,614 | Estimated |
| Engaged | 821.4 | 274,035 | Estimated |
| SQL | 410.7 | 548,070 | Estimated |
| Demo | 287.5 | 782,957 | Estimated |
| Proposal | 172.5 | 1,304,928 | Estimated |
| Won | 69.0 | 3,262,319 | Real |

#### 2024-05  (Won 66, spend 235,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,455.4 | 95,750 | Estimated |
| Working | 1,964.3 | 119,687 | Estimated |
| Engaged | 785.7 | 299,218 | Estimated |
| SQL | 392.9 | 598,436 | Estimated |
| Demo | 275.0 | 854,909 | Estimated |
| Proposal | 165.0 | 1,424,848 | Estimated |
| Won | 66.0 | 3,562,121 | Real |

#### 2024-06  (Won 84, spend 200,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 3,125.0 | 64,000 | Estimated |
| Working | 2,500.0 | 80,000 | Estimated |
| Engaged | 1,000.0 | 200,000 | Estimated |
| SQL | 500.0 | 400,000 | Estimated |
| Demo | 350.0 | 571,429 | Estimated |
| Proposal | 210.0 | 952,381 | Estimated |
| Won | 84.0 | 2,380,952 | Real |

#### 2024-07  (Won 48, spend 180,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,785.7 | 100,800 | Estimated |
| Working | 1,428.6 | 126,000 | Estimated |
| Engaged | 571.4 | 315,000 | Estimated |
| SQL | 285.7 | 630,000 | Estimated |
| Demo | 200.0 | 900,000 | Estimated |
| Proposal | 120.0 | 1,500,000 | Estimated |
| Won | 48.0 | 3,750,000 | Real |

#### 2024-08  (Won 56, spend 190,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 2,083.3 | 91,200 | Estimated |
| Working | 1,666.7 | 114,000 | Estimated |
| Engaged | 666.7 | 285,000 | Estimated |
| SQL | 333.3 | 570,000 | Estimated |
| Demo | 233.3 | 814,286 | Estimated |
| Proposal | 140.0 | 1,357,143 | Estimated |
| Won | 56.0 | 3,392,857 | Real |

#### 2024-09  (Won 49, spend 185,100,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,822.9 | 101,541 | Estimated |
| Working | 1,458.3 | 126,926 | Estimated |
| Engaged | 583.3 | 317,314 | Estimated |
| SQL | 291.7 | 634,629 | Estimated |
| Demo | 204.2 | 906,612 | Estimated |
| Proposal | 122.5 | 1,511,020 | Estimated |
| Won | 49.0 | 3,777,551 | Real |

#### 2024-10  (Won 50, spend 200,000,000)

| Stage | Count | Cost per unit | Real or estimated |
|---|---|---|---|
| New | 1,860.1 | 107,520 | Estimated |
| Working | 1,488.1 | 134,400 | Estimated |
| Engaged | 595.2 | 336,000 | Estimated |
| SQL | 297.6 | 672,000 | Estimated |
| Demo | 208.3 | 960,000 | Estimated |
| Proposal | 125.0 | 1,600,000 | Estimated |
| Won | 50.0 | 4,000,000 | Real |

## 2. New customers vs. industry, customer payments and S&M spend

### Monthly table (spend columns in millions; new revenue in full units)

| Month | Won | Won Restaurants | Won Retail | Won Manufacturing | Won Technology | Won Professional services | Won Healthcare | New revenue | PaidMedia | Travel | PublicidadNoWeb | Freelance | SoftwareTools | Team | PayrollExpenses | Total spend |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022-02 | 108 | 25 | 19 | 25 | 17 | 16 | 6 | 11,147,081 | 108.1 | 16.1 | 39.1 | 11.5 | 9.2 | 27.6 | 18.4 | 230.0 |
| 2022-03 | 30 | 11 | 4 | 7 | 4 | 1 | 3 | 2,780,439 | 108.1 | 16.1 | 27.6 | 11.5 | 13.8 | 27.6 | 25.3 | 230.0 |
| 2022-04 | 19 | 6 | 4 | 5 | 2 | 0 | 2 | 3,975,300 | 122.2 | 14.1 | 40.0 | 14.1 | 11.8 | 28.2 | 4.7 | 235.1 |
| 2022-05 | 38 | 11 | 8 | 9 | 5 | 3 | 2 | 5,894,203 | 135.0 | 18.9 | 32.4 | 18.9 | 8.1 | 32.4 | 24.3 | 270.0 |
| 2022-06 | 33 | 7 | 6 | 11 | 6 | 0 | 3 | 2,674,000 | 105.8 | 14.1 | 37.6 | 14.1 | 14.1 | 28.2 | 21.2 | 235.1 |
| 2022-07 | 32 | 8 | 7 | 8 | 3 | 4 | 2 | 5,484,038 | 88.0 | 13.2 | 30.8 | 19.8 | 13.2 | 26.4 | 28.6 | 220.0 |
| 2022-08 | 26 | 7 | 4 | 7 | 3 | 3 | 2 | 2,553,621 | 130.0 | 19.5 | 55.3 | 22.8 | 9.8 | 39.0 | 48.7 | 325.1 |
| 2022-09 | 17 | 4 | 5 | 4 | 2 | 2 | 0 | 1,347,150 | 150.5 | 24.5 | 63.0 | 28.0 | 14.0 | 42.0 | 28.0 | 350.0 |
| 2022-10 | 32 | 9 | 5 | 8 | 5 | 0 | 5 | 2,252,250 | 146.3 | 26.3 | 45.0 | 33.8 | 18.8 | 45.0 | 60.0 | 375.2 |
| 2022-11 | 19 | 5 | 2 | 5 | 2 | 3 | 2 | 1,474,725 | 150.0 | 21.0 | 42.0 | 27.0 | 9.0 | 36.0 | 15.0 | 300.0 |
| 2022-12 | 26 | 10 | 4 | 6 | 5 | 1 | 0 | 6,569,241 | 130.0 | 19.5 | 52.0 | 22.8 | 9.8 | 39.0 | 52.0 | 325.1 |
| 2023-01 | 60 | 15 | 15 | 16 | 8 | 4 | 2 | 3,693,081 | 136.5 | 22.8 | 58.5 | 16.3 | 19.5 | 39.0 | 32.5 | 325.1 |
| 2023-02 | 30 | 7 | 7 | 6 | 3 | 4 | 3 | 1,641,990 | 105.0 | 15.0 | 42.5 | 20.0 | 10.0 | 30.0 | 27.5 | 250.0 |
| 2023-03 | 38 | 7 | 9 | 13 | 5 | 2 | 2 | 1,683,150 | 130.5 | 17.4 | 37.7 | 11.6 | 8.7 | 34.8 | 49.3 | 290.0 |
| 2023-04 | 51 | 22 | 13 | 2 | 4 | 7 | 3 | 2,886,870 | 138.7 | 17.7 | 35.4 | 17.7 | 14.8 | 35.4 | 35.4 | 295.1 |
| 2023-05 | 47 | 10 | 19 | 6 | 7 | 3 | 2 | 1,996,050 | 138.0 | 24.2 | 41.4 | 0.0 | 13.8 | 41.4 | 86.3 | 345.1 |
| 2023-06 | 46 | 7 | 14 | 12 | 5 | 2 | 6 | 2,178,540 | 82.8 | 12.6 | 25.2 | 7.2 | 7.2 | 41.2 | 3.8 | 180.0 |
| 2023-07 | 65 | 18 | 18 | 14 | 6 | 5 | 4 | 2,532,600 | 68.3 | 12.3 | 28.0 | 0.0 | 7.0 | 41.5 | 18.0 | 175.1 |
| 2023-08 | 66 | 9 | 17 | 22 | 8 | 6 | 4 | 2,993,130 | 40.0 | 6.6 | 17.6 | 0.0 | 3.3 | 41.6 | 0.9 | 110.0 |
| 2023-09 | 56 | 19 | 11 | 13 | 4 | 9 | 0 | 2,253,550 | 51.3 | 7.5 | 16.3 | 0.0 | 3.8 | 41.9 | 4.4 | 125.2 |
| 2023-10 | 64 | 16 | 19 | 15 | 3 | 8 | 3 | 2,961,945 | 55.4 | 8.1 | 21.6 | 0.0 | 5.4 | 42.3 | 2.3 | 135.1 |
| 2023-11 | 72 | 17 | 15 | 21 | 6 | 8 | 5 | 3,278,191 | 59.8 | 7.8 | 15.6 | 0.0 | 5.2 | 43.2 | -1.6 | 130.0 |
| 2023-12 | 55 | 17 | 12 | 15 | 5 | 3 | 3 | 3,064,950 | 67.5 | 9.0 | 25.5 | 0.0 | 9.0 | 44.3 | -5.3 | 150.0 |
| 2024-01 | 57 | 24 | 13 | 10 | 6 | 0 | 4 | 2,313,788 | 70.3 | 13.0 | 33.3 | 0.0 | 7.4 | 44.2 | 16.9 | 185.1 |
| 2024-02 | 32 | 8 | 5 | 9 | 3 | 1 | 6 | 1,287,466 | 102.0 | 12.0 | 30.0 | 0.0 | 12.0 | 44.3 | -0.3 | 200.0 |
| 2024-03 | 43 | 7 | 11 | 12 | 4 | 2 | 7 | 2,707,393 | 87.5 | 10.5 | 29.8 | 0.0 | 8.8 | 43.2 | -4.7 | 175.1 |
| 2024-04 | 69 | 20 | 17 | 13 | 6 | 8 | 5 | 4,189,594 | 103.5 | 13.5 | 29.3 | 0.0 | 6.8 | 44.2 | 27.8 | 225.1 |
| 2024-05 | 66 | 20 | 14 | 14 | 7 | 8 | 3 | 3,984,672 | 110.5 | 14.1 | 35.3 | 0.0 | 14.1 | 44.5 | 16.6 | 235.1 |
| 2024-06 | 84 | 24 | 21 | 15 | 10 | 8 | 6 | 4,629,580 | 98.0 | 12.0 | 36.0 | 0.0 | 6.0 | 44.7 | 3.3 | 200.0 |
| 2024-07 | 48 | 13 | 5 | 14 | 7 | 6 | 3 | 2,378,775 | 90.0 | 10.8 | 28.8 | 0.0 | 7.2 | 44.8 | -1.6 | 180.0 |
| 2024-08 | 56 | 7 | 23 | 10 | 7 | 5 | 4 | 2,090,917 | 87.4 | 11.4 | 26.6 | 0.0 | 5.7 | 44.9 | 14.0 | 190.0 |
| 2024-09 | 49 | 12 | 17 | 7 | 5 | 5 | 3 | 2,382,899 | 74.0 | 13.0 | 25.9 | 0.0 | 9.3 | 44.9 | 18.0 | 185.1 |
| 2024-10 | 50 | 18 | 7 | 9 | 6 | 5 | 5 | 2,201,333 | 78.0 | 12.0 | 26.0 | 0.0 | 8.0 | 45.3 | 30.7 | 200.0 |
| **Total** | 1584 | 420 | 370 | 363 | 179 | 142 | 110 | 105,482,512 | 3,349.0 | 486.6 | 1,131.1 | 297.1 | 324.6 | 1,293.0 | 700.4 | 7,581.8 |

### Correlation of Won with spend 0 to 3 months earlier (Pearson r)

#### All industries

| Spend column | 0 months earlier | 1 months earlier | 2 months earlier | 3 months earlier |
|---|---|---|---|---|
| PaidMedia | -0.48 | -0.43 | -0.39 | -0.34 |
| Travel | -0.43 | -0.54 | -0.41 | -0.22 |
| PublicidadNoWeb | -0.41 | -0.44 | -0.52 | -0.33 |
| Freelance | -0.60 | -0.57 | -0.62 | -0.51 |
| SoftwareTools | -0.39 | -0.45 | -0.48 | -0.10 |
| Team | +0.27 | +0.20 | +0.53 | +0.60 |
| PayrollExpenses | -0.29 | -0.38 | -0.24 | -0.08 |
| Total spend | -0.48 | -0.50 | -0.42 | -0.26 |
| *Months behind each r* | 33 | 33 | 32 | 31 |
| *|r| needed for a 5% signal* | 0.34 | 0.34 | 0.34 | 0.35 |

#### Restaurants: that industry's Won vs. spend

| Spend column | 0 months earlier | 1 months earlier | 2 months earlier | 3 months earlier |
|---|---|---|---|---|
| PaidMedia | -0.33 | -0.41 | -0.38 | -0.38 |
| Travel | -0.30 | -0.51 | -0.38 | -0.27 |
| PublicidadNoWeb | -0.29 | -0.43 | -0.48 | -0.26 |
| Freelance | -0.46 | -0.47 | -0.49 | -0.37 |
| SoftwareTools | -0.21 | -0.44 | -0.41 | -0.12 |
| Team | +0.24 | +0.18 | +0.37 | +0.50 |
| PayrollExpenses | -0.17 | -0.39 | -0.18 | -0.31 |
| Total spend | -0.32 | -0.47 | -0.38 | -0.33 |
| *Months behind each r* | 33 | 33 | 32 | 31 |
| *|r| needed for a 5% signal* | 0.34 | 0.34 | 0.34 | 0.35 |

#### Retail: that industry's Won vs. spend

| Spend column | 0 months earlier | 1 months earlier | 2 months earlier | 3 months earlier |
|---|---|---|---|---|
| PaidMedia | -0.44 | -0.33 | -0.25 | -0.17 |
| Travel | -0.34 | -0.45 | -0.29 | -0.10 |
| PublicidadNoWeb | -0.38 | -0.41 | -0.39 | -0.13 |
| Freelance | -0.62 | -0.53 | -0.49 | -0.37 |
| SoftwareTools | -0.36 | -0.34 | -0.44 | +0.06 |
| Team | +0.36 | +0.29 | +0.40 | +0.42 |
| PayrollExpenses | -0.15 | -0.25 | -0.12 | +0.02 |
| Total spend | -0.40 | -0.38 | -0.29 | -0.11 |
| *Months behind each r* | 33 | 33 | 32 | 31 |
| *|r| needed for a 5% signal* | 0.34 | 0.34 | 0.34 | 0.35 |

#### Manufacturing: that industry's Won vs. spend

| Spend column | 0 months earlier | 1 months earlier | 2 months earlier | 3 months earlier |
|---|---|---|---|---|
| PaidMedia | -0.55 | -0.48 | -0.35 | -0.30 |
| Travel | -0.51 | -0.49 | -0.31 | -0.15 |
| PublicidadNoWeb | -0.42 | -0.38 | -0.44 | -0.43 |
| Freelance | -0.49 | -0.46 | -0.48 | -0.42 |
| SoftwareTools | -0.43 | -0.47 | -0.30 | -0.20 |
| Team | +0.16 | +0.12 | +0.44 | +0.45 |
| PayrollExpenses | -0.44 | -0.36 | -0.29 | +0.17 |
| Total spend | -0.56 | -0.49 | -0.38 | -0.19 |
| *Months behind each r* | 33 | 33 | 32 | 31 |
| *|r| needed for a 5% signal* | 0.34 | 0.34 | 0.34 | 0.35 |

#### Technology: that industry's Won vs. spend

| Spend column | 0 months earlier | 1 months earlier | 2 months earlier | 3 months earlier |
|---|---|---|---|---|
| PaidMedia | -0.14 | -0.04 | +0.04 | -0.03 |
| Travel | -0.08 | -0.21 | -0.08 | +0.04 |
| PublicidadNoWeb | -0.07 | -0.10 | -0.21 | -0.10 |
| Freelance | -0.30 | -0.22 | -0.32 | -0.23 |
| SoftwareTools | -0.13 | -0.22 | -0.16 | +0.15 |
| Team | +0.03 | -0.07 | +0.39 | +0.41 |
| PayrollExpenses | -0.02 | -0.22 | -0.07 | +0.15 |
| Total spend | -0.13 | -0.16 | -0.06 | +0.03 |
| *Months behind each r* | 33 | 33 | 32 | 31 |
| *|r| needed for a 5% signal* | 0.34 | 0.34 | 0.34 | 0.35 |

#### Professional services: that industry's Won vs. spend

| Spend column | 0 months earlier | 1 months earlier | 2 months earlier | 3 months earlier |
|---|---|---|---|---|
| PaidMedia | -0.32 | -0.36 | -0.32 | -0.13 |
| Travel | -0.34 | -0.45 | -0.31 | -0.06 |
| PublicidadNoWeb | -0.31 | -0.33 | -0.34 | -0.09 |
| Freelance | -0.35 | -0.39 | -0.45 | -0.37 |
| SoftwareTools | -0.38 | -0.37 | -0.34 | -0.06 |
| Team | +0.07 | +0.04 | +0.39 | +0.51 |
| PayrollExpenses | -0.24 | -0.26 | -0.19 | -0.11 |
| Total spend | -0.35 | -0.39 | -0.32 | -0.12 |
| *Months behind each r* | 33 | 33 | 32 | 31 |
| *|r| needed for a 5% signal* | 0.34 | 0.34 | 0.34 | 0.35 |

#### Healthcare: that industry's Won vs. spend

| Spend column | 0 months earlier | 1 months earlier | 2 months earlier | 3 months earlier |
|---|---|---|---|---|
| PaidMedia | -0.32 | -0.18 | -0.25 | -0.42 |
| Travel | -0.36 | -0.15 | -0.33 | -0.43 |
| PublicidadNoWeb | -0.40 | -0.15 | -0.24 | -0.47 |
| Freelance | -0.42 | -0.52 | -0.47 | -0.51 |
| SoftwareTools | -0.20 | +0.01 | -0.35 | -0.26 |
| Team | +0.27 | +0.32 | +0.40 | +0.32 |
| PayrollExpenses | -0.36 | -0.16 | -0.20 | -0.20 |
| Total spend | -0.39 | -0.20 | -0.28 | -0.41 |
| *Months behind each r* | 33 | 33 | 32 | 31 |
| *|r| needed for a 5% signal* | 0.34 | 0.34 | 0.34 | 0.35 |

#### Sensitivity: total spend vs. Won without the 43 customers silver tags as probably already customers

| Months earlier | r (your Won definition) | r (without the 43) | Months |
|---|---|---|---|
| 0 | -0.48 | -0.55 | 33 |
| 1 | -0.50 | -0.54 | 33 |
| 2 | -0.42 | -0.41 | 32 |
| 3 | -0.26 | -0.26 | 31 |

#### Trend check: month-over-month change in Won vs. change in spend

| Spend column | 0 months earlier | 1 months earlier | 2 months earlier | 3 months earlier |
|---|---|---|---|---|
| PaidMedia | +0.01 | -0.09 | +0.15 | -0.13 |
| Total spend | +0.14 | -0.18 | -0.09 | +0.14 |
| *Months behind each r* | 32 | 32 | 31 | 30 |

| Period | Months | Won | Won per month | Total spend per month | Cost per Won |
|---|---|---|---|---|---|
| 2022-02 to 2023-05 | 16 | 606 | 37.9 | 287,556,250 | 7,592,244 |
| 2023-06 to 2024-10 | 17 | 978 | 57.5 | 175,347,059 | 3,047,955 |

### Industry profile (all customers)

Average monthly payment = mean of every paid customer-month (amount > 0). Average months paying = paid months per customer up to 2024-10 (recent customers have had less time, so this is a lower bound).

| Industry | Customers | of which Won (new) | Average monthly payment | Average monthly payment without outlier customers | Average months paying |
|---|---|---|---|---|---|
| Restaurants | 529 | 420 | 83,208 | 67,499 | 17.2 |
| Retail | 428 | 370 | 42,327 | 42,327 | 15.1 |
| Manufacturing | 454 | 363 | 63,696 | 63,696 | 17.3 |
| Technology | 241 | 179 | 78,932 | 78,932 | 18.4 |
| Professional services | 165 | 142 | 55,138 | 55,138 | 16.0 |
| Healthcare | 144 | 110 | 75,857 | 75,857 | 17.1 |

