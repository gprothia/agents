---
name: forensic-journal-auditor
metadata:
  category: AuditAndFinancialRisk
  version: 1.0.0
  complexity: Level 3 (Multi-rule Pipeline)
description: >-
  Automates forensic exception testing across ERP General Ledger (GL) journal entry populations.
  Evaluates line-level transactional data against 10 targeted forensic risk rules (Tests A through J),
  calculates multi-flag composite risk scores, and generates prioritized audit sample lists, executive
  summary scorecards, and line-level exception registers to detect fraud, management override,
  duplicate postings, round amounts, recurring digits, and cutoff anomalies.
---

# Forensic Journal Entry Auditor Skill

## 1. Objective & Business Rationale

The **Forensic Journal Entry Auditor** skill automates forensic exception testing across General Ledger (GL) journal entry datasets. It shifts audit workflows from manual or random statistical sampling to 100% data-driven forensic coverage, pinpointing management override of controls, unapproved spreadsheets, weekend postings, cutoff timing anomalies, and suspicious narratives.

### Key Use Cases
1. **Targeted Auditor Follow-up**: 100% automated substantive testing across the entire GL population.
2. **Control Override Detection**: Isolates entries prepared and posted outside automated subledgers (e.g. manual spreadsheets, non-segregated duties).
3. **Multi-Flag Risk Prioritization**: Distinguishes operational noise from fraud patterns by scoring entries that trigger multiple distinct forensic tests.

---

## 2. Input Schema & Derived Fields

### 2.1 Primary Input Schema (`JE_LINE_SOURCE`)

Every source dataset (CSV, BigQuery table, Pandas DataFrame, or ERP extract) must map to these standard fields:

| Field Name | Data Type | Description | Sample / Constraints |
|---|---|---|---|
| `JE_HEADER_ID` | String / Numeric | Unique identifier for the journal entry header | ERP document number / voucher # |
| `FISCAL_PERIOD` | String | Accounting period code | e.g., `SEP-26`, `2026-09` |
| `PREPARED_BY` | String | User ID or username of entry creator | Case-sensitive user string |
| `POSTED_BY` | String | User ID or username of entry approver/poster | Case-sensitive user string |
| `JE_HEADER` | String | Journal entry header description / title | Text |
| `EFFECTIVE_DATE` | Date / String | Accounting effective date of the entry | `YYYY-MM-DD` |
| `DATE_ENTERED` | Date / String | System entry timestamp date | `YYYY-MM-DD` |
| `SOURCE` | String | Subledger or entry source | `Manual`, `Spreadsheet`, `Payroll`, `AP` |
| `FUNCTIONAL_AMOUNT` | Numeric | Net line amount in functional currency | Positives = Debits, Negatives = Credits |
| `AMOUNT_ENTERED` | Numeric | Original transaction amount | Absolute or signed numeric |
| `GL_ACCOUNT` | String | General ledger account number/code | e.g., `401000`, `602000` |
| `ACCOUNT_DESCRIPTION` | String | Classification of account | `Revenue`, `Expense`, `Asset`, `Liability` |
| `BUSINESS_UNIT` | String | Operating unit / Subsidiary identifier | e.g., `US01`, `EU02` |
| `COST_CENTER` | String | Department or cost center allocation | e.g., `CC-1040`, `MKTG-01` |
| `JE_LINE_DESCRIPTION` | String | Line-level narration / description | Text narrative |

### 2.2 Standard Derived Attributes

Compute these attributes during normalization:

- **`FUNC_AMOUNT_DEBIT`**: `CASE WHEN FUNCTIONAL_AMOUNT >= 0 THEN FUNCTIONAL_AMOUNT ELSE 0 END`
- **`FUNC_AMOUNT_CREDIT`**: `CASE WHEN FUNCTIONAL_AMOUNT <= 0 THEN FUNCTIONAL_AMOUNT ELSE 0 END`
- **`ABS_FUNCTIONAL_AMOUNT`**: `ABS(FUNCTIONAL_AMOUNT)`
- **`FISCAL_MONTH`**: `UPPER(SUBSTR(TRIM(FISCAL_PERIOD), 1, 3))` (e.g. `SEP`, `OCT`)
- **`POSTING_DAY_OF_WEEK`**: Day of week derived from `DATE_ENTERED` (`Monday`, ..., `Sunday`)
- **`FUNC_AMOUNT_DEBIT_SUM`**: Header-level aggregation `SUM(FUNC_AMOUNT_DEBIT) OVER (PARTITION BY JE_HEADER_ID)`

---

## 3. Configurable Parameters

| Parameter | Type | Default Value | Description |
|---|---|---|---|
| `AMOUNT_THRESHOLD` | Numeric | `10000.00` | Minimum functional debit sum at header level required to trigger testing |
| `MIN_DESCRIPTION_LENGTH` | Integer | `8` | Maximum string length threshold for short/weak description test |
| `COUNTRY_CODE` | String | `'ALL'` | Scope filter for multi-entity journal extractions |
| `MULTI_FLAG_THRESHOLD` | Integer | `2` | Distinct test flags required to mark `PRIORITY_FOR_TESTING = 'HIGH'` |
| `SUSPICIOUS_KEYWORD_LIST` | Array[String] | *(See Section 5.9)* | Array of forensic and override terms |

---

## 4. End-to-End Execution Pipeline

```
┌────────────────────────────────────────────────────────┐
│ Step 1: Ingestion & Filtering (Filter non-monetary)   │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Step 2: Data Cleaning, Normalization & Derived Fields  │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Step 3: Header-Level Aggregation (FUNC_AMOUNT_DEBIT_SUM)│
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Step 4: Parallel Forensic Exception Testing (Tests A-J)│
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Step 5: Consolidation & Multi-Test Risk Scoring        │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Step 6: Output Generation & Deliverables Export        │
└────────────────────────────────────────────────────────┘
```

---

## 5. Forensic Exception Logic Specifications (Tests A through J)

Common prerequisite for tests:
> **Standard Prerequisite Filter**:
> `FUNC_AMOUNT_DEBIT_SUM >= AMOUNT_THRESHOLD AND PREPARED_BY <> POSTED_BY AND ABS_FUNCTIONAL_AMOUNT > 0`

### 5.1 Test A: Duplicate Journal Entries
- **Objective**: Identify identical line-level postings posted across distinct journal entry headers.
- **Logic**: Match records across different `JE_HEADER_ID` where `GL_ACCOUNT`, `AMOUNT_ENTERED`, `BUSINESS_UNIT`, `COST_CENTER`, and `FISCAL_PERIOD` are identical.
- **Prerequisites**: Standard Prerequisite Filter.
- **Output Flag**: `DUPLICATE_JE`

### 5.2 Test B: Duplicate Journal Entries by Absolute Amount
- **Objective**: Identify offsetting or duplicated amounts entered with inverted signs.
- **Logic**: Match records across different `JE_HEADER_ID` on `GL_ACCOUNT`, `BUSINESS_UNIT`, `COST_CENTER`, `FISCAL_PERIOD`, and `ABS_FUNCTIONAL_AMOUNT`.
- **Prerequisites**: Standard Prerequisite Filter.
- **Output Flag**: `DUPLICATE_JE_ABS_AMOUNT`

### 5.3 Test C: Short or Blank Descriptions
- **Objective**: Detect journal entries lacking sufficient business justification.
- **Logic**: `LENGTH(TRIM(COALESCE(JE_LINE_DESCRIPTION, ''))) <= MIN_DESCRIPTION_LENGTH`
- **Prerequisites**: Standard Prerequisite Filter.
- **Output Flag**: `SHORT_DESCRIPTION`

### 5.4 Test D: Round-Dollar Amounts
- **Objective**: Uncover manual estimated or fictitious postings lacking transaction precision.
- **Logic**: `MOD(CAST(ROUND(ABS_FUNCTIONAL_AMOUNT) AS INT64), 10) = 0 AND ABS_FUNCTIONAL_AMOUNT = ROUND(ABS_FUNCTIONAL_AMOUNT, 0)` (e.g. $10,000.00, $50,250.00).
- **Prerequisites**: Standard Prerequisite Filter.
- **Output Flag**: `ROUND_DOLLAR`

### 5.5 Test E: Recurring Trailing Digits
- **Objective**: Flag repeated trailing digits indicative of artificial numbers (e.g., $15,555.12, $2,222.00).
- **Logic**: Convert `ABS_FUNCTIONAL_AMOUNT` to integer cents/digits without decimal separator, extract the rightmost 3 digits (`TRAILING_DIGITS_NUM`). Trigger when:
  `MOD(TRAILING_DIGITS_NUM, 111) = 0 AND MOD(CAST(FLOOR(ABS_FUNCTIONAL_AMOUNT) AS INT64), 10) <> 0`
- **Prerequisites**: Standard Prerequisite Filter.
- **Output Flag**: `RECURRING_DIGITS`

### 5.6 Test F: Large Quarter-End Revenue Credits
- **Objective**: Detect aggressive revenue recognition or premature accruals posted at fiscal quarter close.
- **Logic**: `FISCAL_MONTH IN ('SEP', 'DEC', 'MAR', 'JUN') AND ACCOUNT_DESCRIPTION = 'Revenue' AND FUNC_AMOUNT_CREDIT < 0 AND SOURCE IN ('Spreadsheet', 'Manual')`
- **Prerequisites**: `FUNC_AMOUNT_DEBIT_SUM >= AMOUNT_THRESHOLD AND PREPARED_BY <> POSTED_BY`
- **Output Flag**: `LARGE_REVENUE_CREDIT`

### 5.7 Test G: Large First-Month Revenue Debits
- **Objective**: Detect quarter-end reversals indicating unauthorized period-end window dressing.
- **Logic**: `FISCAL_MONTH IN ('OCT', 'JAN', 'APR', 'JUL') AND ACCOUNT_DESCRIPTION = 'Revenue' AND FUNC_AMOUNT_DEBIT > 0 AND SOURCE IN ('Spreadsheet', 'Manual')`
- **Prerequisites**: `FUNC_AMOUNT_DEBIT_SUM >= AMOUNT_THRESHOLD AND PREPARED_BY <> POSTED_BY`
- **Output Flag**: `LARGE_REVENUE_DEBIT`

### 5.8 Test H: Large Credits to Expense Accounts
- **Objective**: Uncover improper expense suppression, capitalization, or reversal to inflate earnings.
- **Logic**: `ACCOUNT_DESCRIPTION = 'Expense' AND FUNC_AMOUNT_CREDIT < 0 AND SOURCE IN ('Spreadsheet', 'Manual')`
- **Prerequisites**: `FUNC_AMOUNT_DEBIT_SUM >= AMOUNT_THRESHOLD AND PREPARED_BY <> POSTED_BY`
- **Output Flag**: `LARGE_EXPENSE_CREDIT`

### 5.9 Test I: Suspicious Keyword Search
- **Objective**: Identify descriptions referencing adjustments, executive overrides, audit pressure, or fraud indicators.
- **Logic**: Case-insensitive regex/substring match of `JE_LINE_DESCRIPTION` or `JE_HEADER` against the Master Keyword Library.
- **Prerequisites**: `FUNC_AMOUNT_DEBIT_SUM >= AMOUNT_THRESHOLD AND PREPARED_BY <> POSTED_BY`
- **Output Flag**: `SUSPICIOUS_KEYWORD`

#### Master Keyword Library:
```
reversal, adj, missing, duplicate, adjustment, accrual, audit, bribe, bury, capital, classif, conceal,
confident, contingenc, correct, corrupt, cover, coverup, cover-up, cushion, defer, deficit, delete,
demand, deterioration, dummy, early, EBIT, EBITDA, embezzle, error, ESTD, estimate, facilitation,
fictitious, fix, fraud, fudge, gift, hidden, hide, holdback, immaterial, impair, improper, inappro,
increase, kickback, kitty, manage earnings, manip, mis, misstate, mistake, not deductible, opportunit,
per CEO, per CFO, plug, political gift, problem, quota, rainy day, recl, reclass, recls, reconcile,
reduce, reduct, remov, reserve, restate, restructur, rev, reverse, risks, screen, secret, smooth,
spread, suspen, slu, temp, test, transf, true up, tsfr, txfr, unsupported, write-off
```

### 5.10 Test J: Weekend Postings
- **Objective**: Detect journal entries entered outside standard business operating hours.
- **Logic**: `POSTING_DAY_OF_WEEK IN ('Saturday', 'Sunday')`
- **Prerequisites**: `FUNC_AMOUNT_DEBIT_SUM >= AMOUNT_THRESHOLD AND ABS_FUNCTIONAL_AMOUNT > 0`
- **Output Flag**: `WEEKEND_POSTING`

---

## 6. Multi-Flag Risk Scoring & Aggregation

1. Append all individual test findings into `CONSOLIDATED_EXCEPTION_TABLE`.
2. Group records by `JE_HEADER_ID` and compute distinct test triggers:
   ```sql
   TEST_COUNT = COUNT(DISTINCT TEST_FLAG)
   ```
3. Assign Multi-Flag Evaluation:
   - `MULTI_TEST_FLAG`: Set to `'Yes'` if `TEST_COUNT >= 2`, otherwise `'No'`.
   - `PRIORITY_FOR_TESTING`: Set to `'HIGH'` if `MULTI_TEST_FLAG = 'Yes'`, otherwise `'STANDARD'`.

---

## 7. Deliverable Outputs & Reporting Schema

### Deliverable 1: Executive Summary Scorecard
High-level summary metrics for audit leadership:
- Total population line count and total value ($ Debits / $ Credits)
- Exception rate (% of total lines and % of total headers flagged)
- Multi-Flag Concentration (% of headers with `TEST_COUNT >= 2`)
- Top triggered tests ranking
- Highest-risk preparers (count of high-priority exceptions grouped by `PREPARED_BY`)

### Deliverable 2: Priority Audit Sample
Focused high-risk sample for substantive voucher testing:
- Columns: `JE_HEADER_ID`, `TEST_COUNT`, `TRIGGERED_TESTS`, `FUNC_AMOUNT_DEBIT_SUM`, `PREPARED_BY`, `POSTED_BY`, `SOURCE`, `EFFECTIVE_DATE`, `PRIORITY_FOR_TESTING`

### Deliverable 3: Line-Level Exception Register
Full technical exception dataset for reconciliation:
- Columns: All original `JE_LINE_SOURCE` fields + `TEST_FLAG`, `TRIGGERED_REASON`, `ABS_FUNCTIONAL_AMOUNT`

### Deliverable 4: Individual Test Breakdowns
Sub-tables segmented by test category (Tests A through J) with grouping summaries.

---

## 8. Reference Implementation (BigQuery SQL)

When executing in BigQuery or Spark SQL, use this CTE pipeline pattern:

```sql
WITH base_normalized AS (
  SELECT
    *,
    CASE WHEN FUNCTIONAL_AMOUNT >= 0 THEN FUNCTIONAL_AMOUNT ELSE 0 END AS FUNC_AMOUNT_DEBIT,
    CASE WHEN FUNCTIONAL_AMOUNT <= 0 THEN FUNCTIONAL_AMOUNT ELSE 0 END AS FUNC_AMOUNT_CREDIT,
    ABS(FUNCTIONAL_AMOUNT) AS ABS_FUNCTIONAL_AMOUNT,
    UPPER(SUBSTR(TRIM(FISCAL_PERIOD), 1, 3)) AS FISCAL_MONTH,
    FORMAT_DATE('%A', PARSE_DATE('%Y-%m-%d', CAST(DATE_ENTERED AS STRING))) AS POSTING_DAY_OF_WEEK
  FROM `{project}.{dataset}.JE_LINE_SOURCE`
  WHERE SOURCE != 'STAT' -- Purge non-monetary statistical lines
),
header_totals AS (
  SELECT
    *,
    SUM(FUNC_AMOUNT_DEBIT) OVER(PARTITION BY JE_HEADER_ID) AS FUNC_AMOUNT_DEBIT_SUM
  FROM base_normalized
),
filtered_base AS (
  SELECT *
  FROM header_totals
  WHERE FUNC_AMOUNT_DEBIT_SUM >= 10000.00
),
-- Test A: Duplicate Entries
test_a AS (
  SELECT a.*, 'DUPLICATE_JE' AS TEST_FLAG, 'Identical posting in another header' AS TRIGGERED_REASON
  FROM filtered_base a
  WHERE PREPARED_BY <> POSTED_BY AND ABS_FUNCTIONAL_AMOUNT > 0
    AND EXISTS (
      SELECT 1 FROM filtered_base b
      WHERE b.JE_HEADER_ID <> a.JE_HEADER_ID
        AND b.GL_ACCOUNT = a.GL_ACCOUNT
        AND b.AMOUNT_ENTERED = a.AMOUNT_ENTERED
        AND b.BUSINESS_UNIT = a.BUSINESS_UNIT
        AND b.COST_CENTER = a.COST_CENTER
        AND b.FISCAL_PERIOD = a.FISCAL_PERIOD
    )
),
-- Test C: Short/Blank Descriptions
test_c AS (
  SELECT *, 'SHORT_DESCRIPTION' AS TEST_FLAG, 'Description length <= 8 or null' AS TRIGGERED_REASON
  FROM filtered_base
  WHERE PREPARED_BY <> POSTED_BY AND ABS_FUNCTIONAL_AMOUNT > 0
    AND (LENGTH(TRIM(COALESCE(JE_LINE_DESCRIPTION, ''))) <= 8 OR JE_LINE_DESCRIPTION IS NULL)
),
-- Test D: Round Dollar
test_d AS (
  SELECT *, 'ROUND_DOLLAR' AS TEST_FLAG, 'Round dollar amount ending in 0' AS TRIGGERED_REASON
  FROM filtered_base
  WHERE PREPARED_BY <> POSTED_BY AND ABS_FUNCTIONAL_AMOUNT > 0
    AND MOD(CAST(ROUND(ABS_FUNCTIONAL_AMOUNT) AS INT64), 10) = 0
    AND ABS_FUNCTIONAL_AMOUNT = ROUND(ABS_FUNCTIONAL_AMOUNT, 0)
),
-- Test F: Large Quarter-End Revenue Credits
test_f AS (
  SELECT *, 'LARGE_REVENUE_CREDIT' AS TEST_FLAG, 'Quarter-end revenue credit from manual/spreadsheet source' AS TRIGGERED_REASON
  FROM filtered_base
  WHERE PREPARED_BY <> POSTED_BY
    AND FISCAL_MONTH IN ('SEP', 'DEC', 'MAR', 'JUN')
    AND ACCOUNT_DESCRIPTION = 'Revenue'
    AND FUNC_AMOUNT_CREDIT < 0
    AND SOURCE IN ('Spreadsheet', 'Manual')
),
-- Test I: Suspicious Keywords
test_i AS (
  SELECT *, 'SUSPICIOUS_KEYWORD' AS TEST_FLAG, 'Matched suspicious keyword library' AS TRIGGERED_REASON
  FROM filtered_base
  WHERE PREPARED_BY <> POSTED_BY
    AND REGEXP_CONTAINS(LOWER(CONCAT(COALESCE(JE_LINE_DESCRIPTION, ''), ' ', COALESCE(JE_HEADER, ''))),
      r'\b(reversal|adj|missing|duplicate|adjustment|accrual|audit|bribe|bury|capital|classif|conceal|confident|contingenc|correct|corrupt|cover|coverup|cover-up|cushion|defer|deficit|delete|demand|deterioration|dummy|early|ebit|ebitda|embezzle|error|estd|estimate|facilitation|fictitious|fix|fraud|fudge|gift|hidden|hide|holdback|immaterial|impair|improper|inappro|increase|kickback|kitty|manage earnings|manip|mis|misstate|mistake|not deductible|opportunit|per ceo|per cfo|plug|political gift|problem|quota|rainy day|recl|reclass|recls|reconcile|reduce|reduct|remov|reserve|restate|restructur|rev|reverse|risks|screen|secret|smooth|spread|suspen|slu|temp|test|transf|true up|tsfr|txfr|unsupported|write-off)\b')
),
-- Test J: Weekend Postings
test_j AS (
  SELECT *, 'WEEKEND_POSTING' AS TEST_FLAG, 'Posted on Saturday or Sunday' AS TRIGGERED_REASON
  FROM filtered_base
  WHERE ABS_FUNCTIONAL_AMOUNT > 0
    AND POSTING_DAY_OF_WEEK IN ('Saturday', 'Sunday')
),
-- Union all tests into Consolidated Exception Register
consolidated_exceptions AS (
  SELECT * FROM test_a
  UNION ALL
  SELECT * FROM test_c
  UNION ALL
  SELECT * FROM test_d
  UNION ALL
  SELECT * FROM test_f
  UNION ALL
  SELECT * FROM test_i
  UNION ALL
  SELECT * FROM test_j
),
scored_headers AS (
  SELECT
    JE_HEADER_ID,
    COUNT(DISTINCT TEST_FLAG) AS TEST_COUNT,
    STRING_AGG(DISTINCT TEST_FLAG, ', ') AS TRIGGERED_TESTS,
    MAX(FUNC_AMOUNT_DEBIT_SUM) AS FUNC_AMOUNT_DEBIT_SUM,
    ANY_VALUE(PREPARED_BY) AS PREPARED_BY,
    ANY_VALUE(POSTED_BY) AS POSTED_BY,
    ANY_VALUE(SOURCE) AS SOURCE,
    ANY_VALUE(EFFECTIVE_DATE) AS EFFECTIVE_DATE,
    CASE WHEN COUNT(DISTINCT TEST_FLAG) >= 2 THEN 'HIGH' ELSE 'STANDARD' END AS PRIORITY_FOR_TESTING
  FROM consolidated_exceptions
  GROUP BY JE_HEADER_ID
)
SELECT * FROM scored_headers
ORDER BY TEST_COUNT DESC, FUNC_AMOUNT_DEBIT_SUM DESC;
```

---

## 9. Quality Assurance & Validation Procedures

1. **Population Reconciliation**: Verify total line count and functional debit/credit sum match raw ERP GL extract logs before filtering.
2. **Non-Monetary Exclusion**: Confirm non-monetary / STAT currency rows are purged prior to thresholding.
3. **Completeness of Join**: Ensure header debit sum calculation does not drop split or multi-line journal entries.
4. **Pattern Verification**: Manually test recurring digits on test amounts (e.g. verifying `15,555.12` triggers while `1,230.00` is excluded).
5. **Substantive Spot-Check**: Trace top 10 multi-flagged journal entries directly to ERP workflow approval history and supporting invoices.
