const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, TableOfContents, LevelFormat, convertInchesToTwip,
} = require("docx");

const CW = 9638;            // content width in DXA (A4 minus 2x1134 margins)
const NAVY = "1F3864";
const MIDBLUE = "2E5C8A";
const GREY = "F2F2F2";
const RED = "C00000";
const AMBER = "BF8F00";
const GREEN = "375623";
const MONO = "Consolas";

/* ---------- helpers ---------- */
const H1 = (t) => new Paragraph({ text: t, heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 } });
const H2 = (t) => new Paragraph({ text: t, heading: HeadingLevel.HEADING_2, spacing: { before: 280, after: 120 } });
const H3 = (t) => new Paragraph({ text: t, heading: HeadingLevel.HEADING_3, spacing: { before: 200, after: 80 } });

const P = (t, o = {}) => new Paragraph({
  children: [new TextRun({ text: t, size: o.size || 21, italics: !!o.italics, bold: !!o.bold, color: o.color })],
  spacing: { after: o.after === undefined ? 120 : o.after, line: 276 },
  alignment: o.align,
  indent: o.indent,
});

const RICH = (runs, o = {}) => new Paragraph({
  children: runs.map((r) => new TextRun({
    text: r.t, bold: !!r.b, italics: !!r.i, color: r.c,
    font: r.m ? MONO : undefined, size: r.m ? 19 : 21,
  })),
  spacing: { after: o.after === undefined ? 120 : o.after, line: 276 },
  indent: o.indent,
});

const BUL = (t, lvl = 0) => new Paragraph({
  children: [new TextRun({ text: t, size: 21 })],
  numbering: { reference: "bullets", level: lvl },
  spacing: { after: 70, line: 276 },
});

const BULR = (runs, lvl = 0) => new Paragraph({
  children: runs.map((r) => new TextRun({
    text: r.t, bold: !!r.b, italics: !!r.i, color: r.c,
    font: r.m ? MONO : undefined, size: r.m ? 19 : 21,
  })),
  numbering: { reference: "bullets", level: lvl },
  spacing: { after: 70, line: 276 },
});

// monospace formula block, lightly shaded, indented
const FORM = (lines) => new Table({
  width: { size: CW, type: WidthType.DXA },
  columnWidths: [CW],
  borders: {
    top: { style: BorderStyle.SINGLE, size: 1, color: "D9D9D9" },
    bottom: { style: BorderStyle.SINGLE, size: 1, color: "D9D9D9" },
    left: { style: BorderStyle.SINGLE, size: 12, color: MIDBLUE },
    right: { style: BorderStyle.SINGLE, size: 1, color: "D9D9D9" },
    insideHorizontal: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
    insideVertical: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
  },
  rows: [new TableRow({
    children: [new TableCell({
      width: { size: CW, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: "F7F9FC" },
      margins: { top: 110, bottom: 110, left: 170, right: 140 },
      children: lines.map((l) => new Paragraph({
        children: [new TextRun({ text: l, font: MONO, size: 19 })],
        spacing: { after: 40 },
      })),
    })],
  })],
});

function tbl(headers, rows, widths, opts = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  if (total !== CW) throw new Error(`widths sum ${total} != ${CW}`);
  const head = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: NAVY },
      margins: { top: 80, bottom: 80, left: 110, right: 110 },
      children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, color: "FFFFFF", size: 19 })] })],
    })),
  });
  const body = rows.map((r, ri) => new TableRow({
    children: r.map((c, i) => {
      const cell = typeof c === "object" && c !== null ? c : { t: String(c) };
      return new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: ri % 2 ? GREY : "FFFFFF" },
        margins: { top: 80, bottom: 80, left: 110, right: 110 },
        children: [new Paragraph({
          children: [new TextRun({
            text: cell.t, bold: !!cell.b, color: cell.c,
            font: cell.m || opts.mono ? MONO : undefined,
            size: cell.m || opts.mono ? 18 : 19,
          })],
        })],
      });
    }),
  }));
  return new Table({
    width: { size: CW, type: WidthType.DXA },
    columnWidths: widths,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 2, color: NAVY },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: NAVY },
      left: { style: BorderStyle.SINGLE, size: 2, color: NAVY },
      right: { style: BorderStyle.SINGLE, size: 2, color: NAVY },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: "BFBFBF" },
      insideVertical: { style: BorderStyle.SINGLE, size: 1, color: "BFBFBF" },
    },
    rows: [head, ...body],
  });
}

const SP = (n = 120) => new Paragraph({ children: [], spacing: { after: n } });
const RULE = () => new Paragraph({
  children: [],
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: MIDBLUE, space: 1 } },
  spacing: { before: 60, after: 180 },
});

// per-metric methodology block
function metric({ id, name, category, formula, threshold, current, impl, limits, target }) {
  const out = [H3(`${id}  ${name}`)];
  out.push(RICH([
    { t: "Category: ", b: true }, { t: category },
    { t: "   |   Threshold: ", b: true }, { t: threshold },
    { t: "   |   Current value: ", b: true }, { t: current, m: true },
  ], { after: 100 }));
  out.push(FORM(formula));
  out.push(SP(100));
  out.push(RICH([{ t: "As implemented. ", b: true }, { t: impl }]));
  out.push(RICH([{ t: "Limitations.", b: true }], { after: 50 }));
  limits.forEach((l) => out.push(BUL(l)));
  out.push(RICH([{ t: "Production target. ", b: true }, { t: target }], { after: 200 }));
  return out;
}

/* ---------- document body ---------- */
const body = [];

/* ===== cover ===== */
body.push(SP(1600));
body.push(new Paragraph({
  children: [new TextRun({ text: "Fund KRI Monitor", bold: true, size: 58, color: NAVY })],
  alignment: AlignmentType.CENTER, spacing: { after: 100 },
}));
body.push(new Paragraph({
  children: [new TextRun({ text: "Technical Review: Calculation Methodology,", size: 30, color: MIDBLUE })],
  alignment: AlignmentType.CENTER, spacing: { after: 40 },
}));
body.push(new Paragraph({
  children: [new TextRun({ text: "Identified Weaknesses and Development Roadmap", size: 30, color: MIDBLUE })],
  alignment: AlignmentType.CENTER, spacing: { after: 400 },
}));
body.push(RULE());
body.push(new Paragraph({
  children: [new TextRun({ text: "Independent code and methodology review", size: 22, italics: true, color: "595959" })],
  alignment: AlignmentType.CENTER, spacing: { after: 60 },
}));
body.push(new Paragraph({
  children: [new TextRun({ text: "Reviewed build: fund_kri_monitor  |  Review: 20 October 2026  |  Remediation status: 21 October 2026", size: 20, color: "595959" })],
  alignment: AlignmentType.CENTER, spacing: { after: 60 },
}));
body.push(new Paragraph({
  children: [new TextRun({ text: "Status: Prototype — control defects remediated, risk methodology not yet validated", size: 20, bold: true, color: AMBER })],
  alignment: AlignmentType.CENTER, spacing: { after: 1400 },
}));
body.push(new Paragraph({
  children: [new TextRun({ text: "All findings in Section 6 were reproduced by execution against the project's own sample data, and every closure in Section 6.1 was verified the same way.", size: 18, italics: true, color: "808080" })],
  alignment: AlignmentType.CENTER,
}));
body.push(new Paragraph({ children: [new PageBreak()] }));

/* ===== TOC ===== */
body.push(H1("Contents"));
body.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));
body.push(new Paragraph({ children: [new PageBreak()] }));

/* ===== 1. Purpose ===== */
body.push(H1("1. Purpose and Scope"));
body.push(P("This document reviews the fund_kri_monitor prototype from three angles: what the system calculates and how, where the current implementation is defective or methodologically weak, and what a production-grade fund KRI monitoring capability would additionally require."));
body.push(P("The review is based on a full read of the source code and on executing the pipeline against the project's bundled sample portfolio. Every defect recorded in Section 6 was reproduced empirically rather than inferred from reading the code; the reproduction evidence is stated alongside each finding."));
body.push(P("Section 3 is the core reference section. It documents each of the thirteen key risk indicators with its exact formula as implemented, its configured thresholds, the value it produces on the sample portfolio, its limitations, and the production-grade methodology that should eventually replace it. Sections 7 to 8 cover methodological and framework gaps; Section 9 sets out a prioritised remediation roadmap."));
body.push(P("Scope note: this review deliberately goes beyond the self-assessment already recorded in SUPERVISOR_BRIEF.md Section 8. Infrastructure topics already acknowledged there (data sourcing, SQLite versus enterprise database, alert channels, scheduling, access control) are not repeated except where a specific defect was found.", { italics: true }));

/* ===== 2. Assessment summary ===== */
body.push(H1("2. Assessment Summary"));
body.push(P("The prototype is a well-structured minimum viable product. The control loop it implements is the correct one for a fund risk monitoring function:"));
body.push(FORM(["Data load -> Validation -> KRI calculation -> Threshold classification ->", "Alerting -> Event lifecycle -> Audit trail"]));
body.push(SP(140));
body.push(P("The design decision that distinguishes it from most self-built monitoring tools is that threshold exceptions are not merely reported. They are converted into persistent events with a stable identifier, an accountable owner, a due date, a lifecycle state and an audit history. That is the right architectural instinct and it is the main asset of the project."));
body.push(P("The assessment below summarises maturity by dimension."));
body.push(SP(60));
body.push(tbl(
  ["Dimension", "Assessment", "Comment"],
  [
    ["Architecture and separation of concerns", { t: "Strong", c: GREEN, b: true }, "Clean split across kri / report / storage / alerts modules; dataclass result contract."],
    ["Breadth of KRI coverage", { t: "Good", c: GREEN, b: true }, "Thirteen indicators across six risk families plus data quality."],
    ["Exception lifecycle design", { t: "Strong", c: GREEN, b: true }, "Correct intent, now with an enforced transition map, four-eyes on approval, and no automatic closure of an event a person owns."],
    ["Configurability", { t: "Partial", c: AMBER, b: true }, "Thresholds externalised; model parameters hardcoded in source."],
    ["Calculation correctness", { t: "Weak", c: RED, b: true }, "Unchanged. One conceptual error, one statistically degenerate metric, inconsistent denominators. This is the binding constraint."],
    ["Operational robustness", { t: "Partial", c: AMBER, b: true }, "Reruns are now idempotent and collision-proof, but the run still fails hard on partial data and nothing alerts on failure or absence."],
    ["Verification / test coverage", { t: "Good", c: GREEN, b: true }, "107 regression tests covering indicators, validation, idempotency and lifecycle governance; verified from a clean clone."],
    ["Governance and auditability", { t: "Partial", c: AMBER, b: true }, "Identity now resolved from the OS account with a mandatory rationale and both ends of each transition recorded. The audit log remains a mutable table and limit changes are still ungoverned."],
  ],
  [2700, 1750, 5188]
));
body.push(SP(180));
body.push(RICH([
  { t: "Overall verdict. ", b: true },
  { t: "The skeleton is right and the control layer has now been made sound: reruns are idempotent, the lifecycle refuses illegal transitions, and no event a person owns can be closed without a named sign-off, all held in place by 107 regression tests. What remains is the harder half. The risk methodology is still simplified beyond what a limit framework can safely rely on — the VaR rests on twenty-one observations, the drawdown is a constant-weight backcast, and the exposure denominator is inconsistent — and the governance layer beyond the audit trail is still empty. The prototype is now a trustworthy process around numbers that are not yet validated. Stage 2 in Section 9.2 is what closes that gap." },
]));

body.push(new Paragraph({ children: [new PageBreak()] }));

/* ===== 3. Methodology ===== */
body.push(H1("3. KRI Calculation Methodology"));

body.push(H2("3.1 Notation and base quantities"));
body.push(P("All indicators are derived from two inputs: a one-row-per-holding position file and a date-by-asset return matrix. The following notation is used throughout this section."));
body.push(FORM([
  "MV_i    market value of holding i (signed; may be negative for short positions)",
  "m_i     exposure_multiplier of holding i",
  "ADV_i   30-day average daily traded volume of holding i",
  "L_i     liquidity_days of holding i (analyst-supplied estimate)",
  "r_i,t   return of asset i on date t",
  "",
  "NAV   = SUM_i MV_i                      net asset value (signed sum)",
  "GNAV  = SUM_i |MV_i|                     gross asset value (absolute sum)",
  "w_i   = MV_i / NAV                       signed weight",
  "aw_i  = |MV_i| / GNAV                    absolute weight",
  "GE_i  = |MV_i| x |m_i|                   gross exposure of holding i",
  "",
  "R_t   = SUM_i w_i x r_i,t                portfolio return, constant current weights",
  "V_t   = PROD_{s<=t} (1 + R_s)            cumulative index",
  "DD_t  = V_t / MAX_{s<=t} V_s - 1         drawdown path",
]));
body.push(SP(160));
body.push(RICH([
  { t: "Critical structural note on the denominator. ", b: true },
  { t: "Six indicators are normalised by GNAV (concentration, top-five concentration, largest asset class, liquidity ratio, illiquid ratio, credit exposure) while three are normalised by NAV (stressed liquidity ratio, leverage, derivative exposure). In the bundled long-only sample NAV and GNAV are both 10,000,000, so the inconsistency is invisible. The first short position introduced into the portfolio will cause these two groups of limits to diverge and become mutually incomparable. A single documented exposure convention must be fixed before the framework is relied upon." },
]));
body.push(SP(120));
body.push(RICH([
  { t: "Critical structural note on R_t. ", b: true },
  { t: "The portfolio return series is constructed by applying today's weights to the entire available return history. This is the correct convention for a forward-looking risk measure such as VaR, because it answers \"what would today's portfolio have lost in past market conditions\". It is not a valid basis for a realised performance statistic. This matters for the maximum drawdown indicator — see 3.2.2." },
]));

body.push(H2("3.2 Market risk and stress testing"));

body.push(...metric({
  id: "KRI-01", name: "One-day 95% historical VaR", category: "Market risk",
  threshold: "warning 2.00% / limit 2.50% (<=)", current: "1.8935%",
  formula: [
    "var_95_1d = | percentile( {R_t : all available t}, 5 ) |",
    "",
    "numpy linear interpolation, equal weighting, no fixed lookback window",
  ],
  impl: "Historical simulation on the constant-current-weight return series, taking the fifth percentile of every observation available in the return file. There is no window-length parameter — the lookback is whatever the input file happens to contain.",
  limits: [
    "With the 21 observations supplied, the interpolation index is 0.05 x (21 - 1) = 1.0 exactly, so the indicator equals the second-worst single daily return and nothing else. It is a one-observation estimate presented as a percentile.",
    "No fixed, governed lookback window. Extending the input file silently changes the meaning of the metric and breaks comparability with yesterday's published figure.",
    "Equal weighting of all historical observations: a stress episode two years old carries the same weight as yesterday, and recent volatility regime shifts are not picked up.",
    "No Expected Shortfall. On this portfolio the mean of the worst 5% of days is 2.5425%, which exceeds the 2.50% hard limit — so the fund reads OK on VaR and BREACH on Expected Shortfall. The choice of metric alone reverses the limit verdict.",
    "No backtesting, no independent model cross-check, no model validation record.",
  ],
  target: "Parameterised rolling window of 250 to 500 business days with a documented minimum; an EWMA-weighted variant (decay around 0.94) reported alongside the equally weighted figure; Expected Shortfall at 97.5% as the primary tail measure with VaR retained for limit continuity; a variance-covariance or Monte Carlo cross-check; and a formal backtest (Kupiec proportion-of-failures plus a Basel traffic-light exception count) run monthly with results retained for model validation.",
}));

body.push(...metric({
  id: "KRI-02", name: "Maximum drawdown", category: "Market risk",
  threshold: "warning 6.00% / limit 8.00% (<=)", current: "6.3976%",
  formula: [
    "max_drawdown = | MIN_t ( DD_t ) |",
    "             = | MIN_t ( V_t / MAX_{s<=t} V_s - 1 ) |",
    "",
    "where V_t is built from CONSTANT CURRENT WEIGHTS, not from actual NAV",
  ],
  impl: "The drawdown path is computed from the same constant-current-weight backcast series used for VaR, over the same 21-day window.",
  limits: [
    "This is a conceptual error, not a tuning issue. The figure is the pro-forma drawdown that today's portfolio would have experienced if it had been held unchanged through the historical window. It is not the fund's realised maximum drawdown, because the fund did not hold these weights over that period.",
    "It is nonetheless labelled \"historical max drawdown\" in the README and reported to a risk committee audience. Presenting a pro-forma statistic as a realised one is a reporting integrity issue.",
    "The window is only 21 days long, so the maximum drawdown of any longer-term episode cannot appear at all. A fund cannot breach an 8% drawdown limit on a 21-day lookback unless it is in acute stress.",
    "The metric is path-dependent on an arbitrary start date (the first row of the return file) with no governance over that start date.",
  ],
  target: "Compute realised maximum drawdown from the official dividend-adjusted NAV-per-share series supplied by the fund administrator, over governed windows (since inception, rolling twelve months, year to date). Retain the constant-weight calculation but rename and report it separately as a pro-forma or ex-ante drawdown indicator so the two are never confused.",
}));

body.push(...metric({
  id: "KRI-03", name: "Annualised 20-day realised volatility", category: "Market risk",
  threshold: "warning 18.00% / limit 25.00% (<=)", current: "14.6140%",
  formula: [
    "volatility_20d = stdev( R_{t-19} ... R_t ; ddof = 0 ) x SQRT(252)",
  ],
  impl: "Population standard deviation of the most recent twenty portfolio returns, annualised by the square root of 252.",
  limits: [
    "Twenty observations give a standard error on the volatility estimate of roughly 16% of the estimate itself. A limit set at 25% is therefore being tested against an estimate whose own confidence interval is wider than the gap between the warning and the limit.",
    "ddof = 0 systematically understates the sample volatility; with n = 20 the bias is small but it is a downward bias on a risk measure, which is the wrong direction for a control.",
    "No comparison against a long-run volatility baseline, so a volatility regime change is indistinguishable from normal sampling noise.",
    "Purely backward-looking. No ex-ante volatility from a factor or covariance model, which is what a forward-looking risk limit should be based on.",
  ],
  target: "Report 20-day, 60-day and 250-day realised volatility together with an EWMA volatility estimate, and add an ex-ante volatility figure from an approved factor covariance model. Set the limit against the ex-ante measure and use the realised series for monitoring and model validation.",
}));

body.push(...metric({
  id: "KRI-04", name: "Equity shock stress loss (-10%)", category: "Stress testing",
  threshold: "warning 4.00% / limit 6.00% (<=)", current: "5.5750%",
  formula: [
    "stress_equity_down_10 = | -0.10 x ( w_Equity + 0.50 x w_Derivative ) |",
    "",
    "where w_Equity     = SUM of w_i over holdings with asset_class = 'Equity'",
    "      w_Derivative = SUM of w_i over holdings with asset_class = 'Derivative'",
    "",
    "the shock (-0.10) and the derivative equity-beta proxy (0.50)",
    "are hardcoded constants in kri.py, not configuration",
  ],
  impl: "A single-factor linear shock applied to the equity weight plus half the derivative weight, on the assumption that derivatives carry a 0.5 equity beta.",
  limits: [
    "Only one scenario exists. There is no interest rate shock, no credit spread shock, no FX shock, no commodity shock and no multi-factor or correlated scenario.",
    "The shock magnitude and the 0.5 derivative beta are magic numbers embedded in source code. Changing a stress assumption requires a code change, which means stress assumptions sit outside the configuration governance that the thresholds enjoy.",
    "The derivative treatment is driven solely by the asset_class label. The sample's only derivative is an interest rate swap, which has no equity sensitivity whatsoever, yet it is assigned a 0.5 equity beta and contributes to the equity stress loss. The result is economically meaningless.",
    "No historical scenario replay and no reverse stress testing, both of which supervisors increasingly expect.",
  ],
  target: "Move to a configuration-driven scenario matrix with instrument-level sensitivities: equity shocks by region and sector, parallel and non-parallel rate shocks (+/-100bp, steepener, flattener), credit spread widening by rating band, FX shocks, and a correlation-breakdown scenario. Add historical replays (2008 global financial crisis, March 2020, the 2022 rate shock) and reverse stress tests that solve for the shock magnitude required to breach each limit.",
}));

body.push(H2("3.3 Concentration"));

body.push(...metric({
  id: "KRI-05", name: "Largest single-position concentration", category: "Concentration",
  threshold: "warning 15.00% / limit 20.00% (<=)", current: "22.0000%  (BREACH)",
  formula: ["concentration = MAX_i ( aw_i ) = MAX_i ( |MV_i| / GNAV )"],
  impl: "The maximum absolute weight across holdings, keyed on asset_id.",
  limits: [
    "Keyed on instrument, not on issuer. Equity and bonds of the same issuer, or two share classes of the same company, are counted as separate exposures, so true issuer concentration is systematically understated.",
    "No look-through into collective investment undertakings. The sample's high yield credit ETF is treated as a single 13% line item when it in fact represents several hundred underlying issuers; conversely a concentrated fund holding would hide a genuine issuer breach.",
    "No aggregation across a group of connected clients or ultimate parent hierarchy.",
    "The limit is a single internal number. It is not mapped to the applicable regulatory or prospectus issuer caps, so a regulatory breach and an internal appetite breach are indistinguishable in the output.",
  ],
  target: "Add issuer_id and ultimate_parent_id to the position schema, aggregate at both levels, apply look-through for funds and ETFs, and express the limit as a three-tier structure (regulatory cap, prospectus cap, internal appetite) so the escalation path can differ by tier.",
}));

body.push(...metric({
  id: "KRI-06", name: "Top-five concentration", category: "Concentration",
  threshold: "warning 65.00% / limit 75.00% (<=)", current: "83.0000%  (BREACH)",
  formula: ["top5_concentration = SUM of the five largest aw_i"],
  impl: "Sum of the five largest absolute weights, capped at the number of holdings available.",
  limits: [
    "The threshold is not calibrated to portfolio size. The sample holds eight positions, so the top five will structurally represent a very large share of the portfolio regardless of how well diversified the manager actually is. The reported BREACH is an artefact of position count, not of risk-taking.",
    "Inherits the instrument-versus-issuer and look-through weaknesses of KRI-05.",
    "A fixed top-n measure is not comparable across funds with different mandated position counts, which makes it unusable as a firm-wide KRI.",
  ],
  target: "Replace or supplement with a size-independent diversification measure — the Herfindahl-Hirschman index (SUM aw_i squared) and the effective number of holdings (1 / SUM aw_i squared) — and calibrate any retained top-n limit per mandate against the expected position count stated in the prospectus.",
}));

body.push(...metric({
  id: "KRI-07", name: "Largest asset class exposure", category: "Concentration",
  threshold: "warning 45.00% / limit 55.00% (<=)", current: "54.0000%  (WATCH)",
  formula: [
    "largest_asset_class = MAX over classes c of ( | SUM_{i in c} MV_i | / GNAV )",
  ],
  impl: "Groups holdings by the asset_class text field, sums market value within each class, takes the absolute value, divides by GNAV, and takes the maximum.",
  limits: [
    "asset_class is an uncontrolled free-text column in the CSV. A spelling variation such as \"Equities\" instead of \"Equity\" silently creates a new class. This does not raise an error — it quietly changes this indicator and simultaneously removes the affected holdings from the equity stress test in KRI-04. This is a silent control failure with no detection mechanism.",
    "Only asset class is monitored. There is no sector, geography, currency, rating-band or counterparty concentration indicator.",
    "Taking the absolute value of a signed class total means a long and a short within the same class net to a small number and can mask large gross two-way exposure.",
  ],
  target: "Enforce a controlled vocabulary for asset_class as a data quality check that fails the run, and extend concentration monitoring to sector, country, currency and rating dimensions driven by reference data rather than a hand-maintained text field.",
}));

body.push(H2("3.4 Liquidity"));
body.push(RICH([
  { t: "Framework-level finding. ", b: true },
  { t: "The project contains two mutually inconsistent definitions of liquidity that are never reconciled. KRI-08 uses the analyst-supplied liquidity_days field and reports 87.50% of the portfolio as liquid within five days. KRI-09 uses a volume-capacity model on the same portfolio and reports 65.63%. Both are presented in the same report with separate limits, and no process exists to explain or resolve the 22 percentage point gap. In addition, the entire liquidity section measures only the asset side; there is no liability-side measurement at all. See Section 8.3." },
]));
body.push(SP(140));

body.push(...metric({
  id: "KRI-08", name: "Five-day liquidity ratio", category: "Liquidity",
  threshold: "warning 40.00% / limit 30.00% (>=)", current: "87.5000%",
  formula: [
    "liquid_within_5d_i = ( L_i <= 5 )",
    "",
    "liquidity_ratio = SUM_{i : L_i <= 5} |MV_i| / GNAV",
  ],
  impl: "A simple flag-and-sum on the liquidity_days input column. The five-day cut-off is a hardcoded constant.",
  limits: [
    "liquidity_days is a manual analyst judgement supplied in the input file. The indicator therefore measures an opinion, not an observable market quantity, and there is no challenge, review or back-testing of those estimates.",
    "Volume capacity is ignored entirely: a position flagged as two-day liquid is counted in full even if its size represents many days of average volume.",
    "Binary cut-off with no liquidity ladder. Holdings in the six-to-ten day range are counted in neither this indicator nor the illiquid indicator (KRI-10), so a material part of the portfolio can be invisible to both.",
    "Normalised by GNAV while the companion stressed measure is normalised by NAV.",
  ],
  target: "Retain liquidity_days only as a reference-data attribute subject to periodic review, and base the published liquidity KRI on a measured time-to-liquidate model. Replace the binary cut-off with a full regulatory-style bucketing ladder (0-1 day, 2-7 days, 8-30 days, 31-90 days, 91-180 days, over 180 days).",
}));

body.push(...metric({
  id: "KRI-09", name: "Stressed five-day liquidity ratio", category: "Liquidity",
  threshold: "warning 25.00% / limit 15.00% (>=)", current: "65.6250%",
  formula: [
    "five_day_liquidity_value_i = MIN( |MV_i| , ADV_i x 0.20 x 5 )",
    "   with an override: if asset_class = 'Cash' then = |MV_i|",
    "",
    "stressed_liquidity_value_i = five_day_liquidity_value_i x 0.75",
    "",
    "stressed_liquidity_ratio   = SUM_i stressed_liquidity_value_i / NAV",
    "",
    "hardcoded constants: participation rate 0.20, horizon 5 days, haircut 0.75",
  ],
  impl: "Assumes the fund can trade 20% of average daily volume per day for five days, caps the liquidatable amount at the position size, and applies a flat 25% stress haircut to the resulting capacity.",
  limits: [
    "The participation rate, the horizon and the stress haircut are all hardcoded in source. These are the three most important assumptions in the model and none of them is governed, versioned or approved.",
    "The capacity model is linear in volume. It ignores market impact convexity, and more importantly it assumes ADV itself is unchanged under stress — in practice liquidity in the stressed asset classes evaporates precisely when the fund needs it, so a flat 25% haircut on an unchanged ADV is optimistic in the wrong direction.",
    "Holdings with ADV of zero (the private equity co-investment and the swap in the sample) contribute zero capacity, which is conservative and reasonable, but the Cash override is applied by asset_class text match and so inherits the free-text fragility described in KRI-07.",
    "A companion field, days_to_liquid_by_adv, is computed for every holding and written to both the Excel output and the database, but is not used by any indicator or threshold. It is dead weight in the published report.",
  ],
  target: "Externalise the participation rate, horizon and haircuts to configuration with per-asset-class granularity; apply stressed ADV assumptions rather than a flat post-hoc haircut; model market impact as a non-linear function of participation; and promote days_to_liquid_by_adv to a monitored indicator with its own limit.",
}));

body.push(...metric({
  id: "KRI-10", name: "Illiquid asset ratio", category: "Liquidity",
  threshold: "warning 20.00% / limit 30.00% (<=)", current: "9.0000%",
  formula: ["illiquid_ratio = SUM_{i : L_i > 10} |MV_i| / GNAV"],
  impl: "Sum of absolute market value of holdings whose liquidity_days exceeds ten, over GNAV. The ten-day cut-off is hardcoded.",
  limits: [
    "Shares the dependence on the analyst-supplied liquidity_days field.",
    "The gap between this indicator's ten-day floor and KRI-08's five-day ceiling leaves the six-to-ten day band unmonitored.",
    "No valuation-risk dimension. The sample holds a private equity co-investment at 9% of NAV with a 90-day liquidity estimate, but there is no indicator for the share of NAV in fair-value Level 3 assets, nor for the age of the latest valuation received from the general partner. Illiquidity and valuation uncertainty are different risks and only one of them is measured.",
    "No side-pocket, gating or suspension indicator.",
  ],
  target: "Add a fair-value hierarchy indicator (share of NAV in Level 2 and Level 3), a valuation staleness indicator (days since last independent valuation per holding), and an indicator for the share of NAV held in assets subject to transfer restrictions or lock-ups.",
}));

body.push(H2("3.5 Credit, leverage and derivatives"));

body.push(...metric({
  id: "KRI-11", name: "Credit exposure", category: "Credit",
  threshold: "warning 20.00% / limit 30.00% (<=)", current: "13.0000%",
  formula: ["credit_exposure = SUM_{i : asset_class = 'Credit'} |MV_i| / GNAV"],
  impl: "A bucket count: the proportion of gross assets whose asset_class label is exactly \"Credit\".",
  limits: [
    "This is an allocation indicator, not a credit risk indicator. It carries no information about the credit quality, spread sensitivity or default probability of the exposure. A portfolio of AAA-rated paper and a portfolio of distressed debt produce an identical reading.",
    "The sample's ten-year US Treasury is labelled \"Bond\", not \"Credit\", so sovereign exposure is excluded from this indicator entirely and is not captured by any other one.",
    "No issuer-level credit exposure, no rating distribution, no rating migration tracking, no watchlist, no spread duration (CS01), no probability of default or loss given default input.",
    "Inherits the free-text asset_class fragility.",
  ],
  target: "Replace the single bucket indicator with a credit risk panel: exposure by rating band with a sub-investment-grade cap, weighted average rating, spread duration, issuer-level top-ten credit exposures, a rating downgrade and migration monitor, and a watchlist exposure indicator.",
}));

body.push(...metric({
  id: "KRI-12", name: "Gross leverage", category: "Leverage",
  threshold: "warning 1.25x / limit 1.50x (<=)", current: "1.0700x",
  formula: [
    "GE_i     = |MV_i| x |m_i|",
    "leverage = SUM_i GE_i / NAV",
    "",
    "worked example from the sample data:",
    "  IRS_SWAP  market_value = 350,000   multiplier = 3.0",
    "            -> GE = 1,050,000",
  ],
  impl: "Sums an exposure figure derived from each holding's mark-to-market value multiplied by a per-holding multiplier, divided by NAV.",
  limits: [
    "The derivative exposure basis is wrong. For a derivative, mark-to-market value and notional exposure are unrelated quantities: a newly struck interest rate swap has a mark-to-market near zero while carrying a large notional. Deriving exposure as mark-to-market times a multiplier produces a number with no economic interpretation, and the reported 1.07x leverage is therefore very likely a false comfort reading.",
    "No distinction between the gross method and the commitment method. A European fund is generally required to calculate and disclose leverage under both, and a UCITS must apply either the commitment approach or a VaR-based approach with its own constraints. One unlabelled multiplier-based number satisfies neither.",
    "No recognition of netting or hedging arrangements, which the commitment method explicitly permits and which materially changes the result for any portfolio using derivatives for risk reduction.",
    "The exposure_multiplier is a manually supplied per-row field with no validation, no reference-data source and no reconciliation to instrument terms.",
  ],
  target: "Source instrument notional, delta and PV01 from the order management or reference data system and compute exposure on that basis. Implement the gross method and the commitment method as two separate, separately-limited indicators, with documented netting and hedging rules, and reconcile both to the leverage figures disclosed in regulatory reporting.",
}));

body.push(...metric({
  id: "KRI-13", name: "Derivative gross exposure", category: "Derivatives",
  threshold: "warning 20.00% / limit 30.00% (<=)", current: "10.5000%",
  formula: ["derivative_exposure = SUM_{i : asset_class = 'Derivative'} GE_i / NAV"],
  impl: "The same multiplier-based gross exposure as KRI-12, restricted to holdings labelled \"Derivative\".",
  limits: [
    "Inherits the mark-to-market versus notional error in full.",
    "No sensitivity measures. There are no Greeks (delta, gamma, vega), no PV01 and no key-rate exposures, so the actual market sensitivity introduced by the derivative book is unmeasured.",
    "No counterparty dimension at all: no counterparty identity in the schema, no counterparty concentration indicator, no uncollateralised mark-to-market exposure.",
    "No collateral or margin monitoring: no initial or variation margin, no collateral haircut, no credit support annex threshold tracking, and crucially no measure of the liquidity drain that a margin call would impose on the fund.",
  ],
  target: "Extend the schema with counterparty, notional, and sensitivity fields; add counterparty concentration and uncollateralised exposure indicators; add a margin-call liquidity stress that links derivative positions back to the liquidity KRIs; and monitor Greeks against a derivatives risk budget.",
}));

body.push(H2("3.6 Threshold classification logic"));
body.push(P("Every indicator is classified by a single shared function that supports two comparison directions."));
body.push(FORM([
  "comparison '<=' (a cap, higher is worse):",
  "    value > limit    -> BREACH",
  "    value > warning  -> WATCH",
  "    otherwise        -> OK",
  "",
  "comparison '>=' (a floor, lower is worse):",
  "    value < limit    -> BREACH",
  "    value < warning  -> WATCH",
  "    otherwise        -> OK",
  "",
  "any other operator -> ValueError",
]));
body.push(SP(140));
body.push(RICH([{ t: "Limitations of the classification layer.", b: true }], { after: 60 }));
body.push(BUL("Only two operators are supported. A range limit (a target band with both an upper and a lower bound) cannot be expressed, which rules out indicators such as a hedge ratio or a duration band."));
body.push(BUL("Classification is strictly point-in-time. There is no deadband and no consecutive-day persistence rule, so an indicator oscillating around its warning level will generate a fresh WATCH, a clear, and another WATCH on successive days. This is the standard cause of alert fatigue and consequent loss of credibility for a monitoring function."));
body.push(BUL("There is no tiering of limit type. A regulatory cap, a prospectus cap and an internal risk appetite trigger are all represented identically, yet they carry entirely different consequences and remediation deadlines."));
body.push(BUL("There is no passive versus active breach classification. A breach caused by market movement in a portfolio that was compliant when traded requires correction without undue delay; a breach caused by a trade is a compliance incident requiring investigation and reporting. The system cannot tell them apart."));
body.push(BUL("No distance-to-limit or velocity measure. The history file accumulates values but nothing computes headroom, the n-day change, the number of consecutive days in breach, or a projection of when a trending indicator will cross its limit. A monitoring dashboard whose primary purpose is early warning should lead with direction and speed, not only level."));
body.push(BUL("Thresholds are read live from config/thresholds.json at every run. A limit can be edited with no approval, no effective date and no version record. The per-run copy of warning and limit stored in the database does preserve what was applied historically, which is a genuine strength, but it does not record who authorised the value or when it took effect."));

body.push(new Paragraph({ children: [new PageBreak()] }));

/* ===== 4. DQ ===== */
body.push(H1("4. Data Quality Check Methodology"));
body.push(P("Six checks are evaluated on every run and published to a dedicated report tab and database table."));
body.push(SP(60));
body.push(tbl(
  ["Check", "Method", "Warning / Limit", "Sample result"],
  [
    ["position_data_age_days", "days between today and max(as_of_date)", "2 / 5  (<=)", { t: "658 — BREACH", c: RED, b: true }],
    ["return_observation_count", "row count of the return matrix", "60 / 20  (>=)", { t: "21 — WATCH", c: AMBER, b: true }],
    ["returns_cover_as_of_date", "max(return date) >= position as_of_date", "boolean", "OK"],
    ["nav_positive", "NAV > 0", "boolean", "OK"],
    ["position_count", "holding count > 0", "boolean", "OK"],
    ["return_window", "informational only, always OK", "n/a", "2024-12-02 to 2024-12-31"],
  ],
  [2500, 3300, 1600, 2238]
));
body.push(SP(180));
body.push(RICH([{ t: "Weaknesses in the data quality layer.", b: true }], { after: 60 }));
body.push(BUL("The BREACH branch of return_observation_count is unreachable. The pipeline raises a hard exception when fewer than twenty return observations are present, and that exception is raised before the data quality frame is built, so the check can only ever report WATCH or OK. The control appears to exist but cannot fire."));
body.push(BUL("as_of_date is taken as the maximum across position rows. If one stale row is carried forward from a previous day, the maximum hides it. The check that all position rows share a single as_of_date does not exist."));
body.push(BUL("The checks are structural rather than reconciliation-based. Nothing is compared against an independent source, so the most common real-world data failure — a position or NAV file that loads cleanly but is wrong — is undetectable."));
body.push(BUL("Absent checks that a production control framework would require: NAV reconciliation against the fund administrator's official NAV within tolerance; day-on-day position count and market value delta against an expected range; per-instrument price staleness; FX rate availability and staleness; corporate action completeness; return outlier detection (for example any absolute daily return beyond five standard deviations); sum-of-weights equals one; controlled vocabulary validation on asset_class; and referential integrity between the position file and reference data."));
body.push(BUL("No data quality score or gate. A BREACH on data age does not prevent the report from being published and distributed as if the numbers were reliable. A production control would either block publication or stamp the report as provisional."));

/* ===== 5. Lifecycle ===== */
body.push(H1("5. Event Lifecycle and Persistence Methodology"));
body.push(P("Any indicator classified WATCH or BREACH becomes an event with a deterministic identifier formed from the fund identifier and the metric name, for example KRI_FUND-CONCENTRATION. On each run the engine upserts the event, so a persistent breach updates one row rather than creating duplicates. Events absent from the current run are automatically cleared. Every system and manual change is written to an audit table."));
body.push(SP(60));
body.push(FORM([
  "event_id = UPPER(fund_id) + '-' + UPPER(metric)",
  "",
  "documented lifecycle:",
  "  NEW -> OPEN -> ACKNOWLEDGED -> INVESTIGATING -> ACTION_PROPOSED",
  "      -> APPROVED -> CLOSED",
  "",
  "additional states written by the engine but absent from the documented flow:",
  "  REOPENED   (set when a CLOSED event re-breaches)",
  "  CLEARED    (set automatically when the metric returns to OK)",
  "",
  "due date:  BREACH -> as_of_date + 1 business day",
  "           WATCH  -> as_of_date + 5 business days",
]));
body.push(SP(160));
body.push(RICH([{ t: "Design strengths.", b: true }], { after: 60 }));
body.push(BUL("Deterministic event identity correctly prevents duplicate issues for a persistent breach."));
body.push(BUL("The per-run snapshot of value, warning and limit means a historical event can be interpreted against the thresholds that actually applied at the time."));
body.push(BUL("Holdings are snapshotted per run, so the composition behind a historical breach is recoverable."));
body.push(SP(80));
body.push(RICH([{ t: "Methodological weaknesses.", b: true }], { after: 60 }));
body.push(BUL("Automatic clearing overrides human state. This was the most serious governance defect in the project; it is documented as D-03 in Section 6 and has since been fixed by the introduction of a PENDING_CLOSURE state. The remaining bullets in this list are still open."));
body.push(BUL("Event identity is reused across distinct breach episodes. If an event is cleared in January and the same metric breaches again in June, the June breach reopens the January row, reuses its first_seen timestamp and nulls its closed_at. The two episodes become one indistinguishable record and the count of discrete breach incidents in a period — a reportable statistic — cannot be derived from the events table at all. It can only be partially reconstructed from the audit log."));
body.push(BUL("Due dates are calculated but never enforced. Nothing reads due_date to identify an overdue event, there is no ageing bucket, and there is no escalation ladder."));
body.push(BUL("The return matrix used for the calculation is not snapshotted. Holdings are preserved per run but the returns are not, so a historical VaR or volatility figure cannot be reproduced from the database once the input CSV has been overwritten by the next day's extract. For a risk figure that may be cited in a regulatory or investor context, this is a reproducibility failure."));
body.push(BUL("The audit log is an ordinary SQLite table in a file with ordinary filesystem permissions. Any user who can run the monitor can also open the database and update or delete audit rows. An audit trail that the subject of the audit can edit does not satisfy any recognised evidential standard."));

body.push(new Paragraph({ children: [new PageBreak()] }));

/* ===== 6. Verified defects ===== */
body.push(H1("6. Verified Defects"));
body.push(P("Each item below was reproduced by executing the project code against its own bundled sample data. The evidence column records the observed behaviour, not an expectation."));
body.push(P("The status column records remediation as at 21 October 2026. Five defects have been fixed and each fix is locked down by regression tests; Section 6.1 records the verification evidence. The remaining eleven are open and carried into the roadmap in Section 9.", { italics: true }));
body.push(SP(60));

const FIXED = { t: "Fixed", c: GREEN, b: true };
const OPEN = { t: "Open", c: AMBER, b: true };

body.push(tbl(
  ["ID", "Defect", "Evidence observed", "Sev", "Status"],
  [
    ["D-01", "Persistence is not idempotent. A same-day rerun appends a second full set of rows; there is no unique constraint and no supersede logic.", "Two runs produced monitor_runs = 2, kri_results = 26 rows (13 expected), holdings_snapshots = 16 rows (8 expected), maximum duplication per as_of_date and metric = 2. Any scheduler retry double-counts every trend query.", { t: "P0", c: RED, b: true }, FIXED],
    ["D-02", "run_id is built with second-level precision, so two runs within the same second collide on the primary key.", "Back-to-back execution raised sqlite3.IntegrityError: UNIQUE constraint failed: monitor_runs.run_id and aborted the run.", { t: "P0", c: RED, b: true }, FIXED],
    ["D-03", "Automatic clearing closes events that are under active human investigation, with no sign-off.", "An event was manually set to INVESTIGATING with the comment \"PM reducing position, remediation in progress\". After the indicator mechanically returned to OK, the next run set it to CLEARED and populated closed_at. The remediation record was closed without any human action.", { t: "P0", c: RED, b: true }, FIXED],
    ["D-04", "The lifecycle state machine is not enforced. Only membership in a state whitelist is validated, not the legality of the transition.", "A direct CLOSED to APPROVED transition was accepted and persisted. The actor field is an unauthenticated free-text CLI argument, so any value can be recorded as the acting party.", { t: "P0", c: RED, b: true }, FIXED],
    ["D-05", "No automated test suite exists anywhere in the project.", "A filesystem search for test files returned no results. For a control system, a silent arithmetic regression is a control failure with no detection mechanism.", { t: "P0", c: RED, b: true }, FIXED],
    ["D-06", "Maximum drawdown is computed from a constant-current-weight backcast and reported as a realised historical statistic.", "Code inspection confirms the drawdown path is derived from the same synthetic return series as VaR. The figure is pro-forma, not realised. See KRI-02.", { t: "P1", c: AMBER, b: true }, OPEN],
    ["D-07", "VaR degenerates to a single observation at the supplied history length.", "With 21 observations the percentile interpolation index is exactly 1.0, so the metric equals the second-worst daily return (-1.8935%). Expected Shortfall on the same data is 2.5425%, above the 2.50% hard limit — the two measures disagree on the limit verdict.", { t: "P1", c: AMBER, b: true }, OPEN],
    ["D-08", "Latent denominator inconsistency between NAV and GNAV across the indicator set.", "In the long-only sample NAV = GNAV = 10,000,000, so the inconsistency is currently masked. It will surface as soon as a short position is introduced, at which point the two groups of limits become incomparable.", { t: "P1", c: AMBER, b: true }, OPEN],
    ["D-09", "The return input is not snapshotted, so historical risk figures cannot be reproduced.", "The schema contains holdings_snapshots but no equivalent table for returns. Once the input CSV is overwritten, a published VaR cannot be recalculated.", { t: "P1", c: AMBER, b: true }, OPEN],
    ["D-10", "Any single missing or non-numeric return series aborts the entire run, producing no report at all.", "Validation raises ValueError on missing asset columns or missing values. A batch failure at 07:30 therefore yields no output whatsoever rather than a degraded report with the affected indicators marked unavailable.", { t: "P1", c: AMBER, b: true }, OPEN],
    ["D-11", "Batch failure is written to a log file with no active alerting; absence of a run is not itself detected.", "The scheduler wrapper captures stderr to outputs/last_scheduler_stderr.log and returns a non-zero exit code. Nothing monitors for a missing or failed run, so a silent outage is indistinguishable from a clean day.", { t: "P1", c: AMBER, b: true }, OPEN],
    ["D-12", "The unreachable data quality BREACH branch described in Section 4.", "The <20 observation condition is enforced by an earlier exception, so the check cannot report BREACH.", { t: "P2", c: MIDBLUE, b: true }, OPEN],
    ["D-13", "Inconsistent time handling. Most timestamps are timezone-aware UTC, but the data age calculation uses a naive local date and the alert header uses a naive local timestamp.", "Code inspection. Creates ambiguity of up to a day in the data age control depending on the host timezone.", { t: "P2", c: MIDBLUE, b: true }, OPEN],
    ["D-14", "Business day offsets use a generic Monday-to-Friday calendar with no holiday awareness.", "Remediation due dates can be set to a public holiday, which is unworkable as an operational deadline in a jurisdiction-specific process.", { t: "P2", c: MIDBLUE, b: true }, OPEN],
    ["D-15", "A computed field, days_to_liquid_by_adv, is published to the report and database but drives no indicator.", "Grep confirms it is written by the calculation module and formatted by the report module, but never referenced in any threshold comparison.", { t: "P2", c: MIDBLUE, b: true }, OPEN],
    ["D-16", "No dependency pinning or environment lock. Requirements specify lower bounds only.", "requirements.txt declares pandas>=2.0.0, numpy>=1.24.0, openpyxl>=3.1.0. A future pandas release altering groupby or percentile behaviour would silently change published risk numbers.", { t: "P2", c: MIDBLUE, b: true }, OPEN],
    ["D-17", "The workbook sheet labelled \"Breach Log\" contains watch items as well as hard-limit breaches.", "Found while writing the regression tests for D-05. On the sample portfolio the sheet reported five rows when two limits had actually failed, overstating the breach count by 150%.", { t: "P1", c: AMBER, b: true }, FIXED],
  ],
  [560, 2300, 4878, 500, 1400]
));

body.push(SP(120));
body.push(H2("6.1 Remediation Evidence"));
body.push(P("The five closed defects were fixed in the same execute-and-observe manner in which they were found. The table records what was run and what was observed afterwards, so the closure can be re-verified independently."));
body.push(SP(60));
body.push(tbl(
  ["ID", "Fix applied", "Verification observed after the fix"],
  [
    ["D-01", "Unique indexes on the business key of every detail table (fund, as-of date, and metric / check / asset respectively); a rerun deletes the superseded detail rows and stamps the previous run with superseded_by_run_id and superseded_at rather than deleting the run header.", "The live database, which already carried the defect, was migrated from 52 / 24 / 32 rows down to 13 / 6 / 8 and stayed flat across three further reruns, with 27 rows superseded each time. A direct duplicate INSERT is now rejected by the database with an IntegrityError."],
    ["D-02", "run_id carries an 8-character random suffix in addition to the UTC timestamp.", "Ten persist operations inside the same clock second produced ten distinct run identifiers and no collision. Previously the second run in a second aborted."],
    ["D-03", "A PENDING_CLOSURE state was introduced. An event in a human-owned state (ACKNOWLEDGED, INVESTIGATING, ACTION_PROPOSED, APPROVED) is moved there when the metric returns to OK, and closed_at is deliberately left null. Only events still in a system-owned state (NEW, OPEN, REOPENED) auto-clear.", "An event in INVESTIGATING now moves to PENDING_CLOSURE with closed_at null, and is still listed as open to the risk team; the run reports it as pending manual closure. Each of the four human-owned states was tested individually. A breach recurring while an event sits in PENDING_CLOSURE reopens it."],
    ["D-04", "An explicit transition map is enforced on every manual change; approving an action proposed by the same identity is rejected; the acting identity is resolved from the operating-system account rather than accepted as a CLI argument; a non-empty rationale is mandatory.", "CLOSED to APPROVED, NEW to APPROVED and the other illegal jumps are rejected with a TransitionError and leave no audit entry. Self-approval is rejected by the four-eyes check and succeeds once a second identity approves. An empty or whitespace-only comment is rejected. The audit log now records from_state, to_state, the acting identity, any on-behalf-of attribution, and the operating-system user and host."],
    ["D-05", "A pytest suite of 107 cases across four files: indicator regression, loader and validation edge cases, persistence idempotency, and lifecycle governance.", "107 passed. Verified from a clean clone of the published repository, not only in the development directory, so the suite does not depend on local state. Warnings are configured as errors, so a pandas deprecation will fail the build rather than pass silently."],
    ["D-17", "The breach register and the watch list are built separately and the workbook carries both as distinct sheets.", "The Breach Log sheet now contains exactly the two hard-limit failures and the Watch List the three early warnings; the two are disjoint and together reconcile to the action plan. Both retain their column headers on a clean day."],
  ],
  [560, 4000, 5078]
));
body.push(SP(120));
body.push(RICH([
  { t: "Scope note. ", b: true },
  { t: "The five closed defects are all control and engineering defects — idempotency, identity, state integrity, and test coverage. None of the open items in the methodology group have been addressed, and they are the ones that determine whether the numbers themselves are right. D-06, D-07 and D-08 in particular should be read as live limitations on the figures in Section 8: the drawdown is pro-forma rather than realised, the VaR rests on a single observation and disagrees with Expected Shortfall on the limit verdict, and the NAV versus gross-NAV inconsistency is masked only because the sample portfolio is long-only. Fixing the governance of the workflow does not make an unvalidated risk number fit to publish." },
]));

body.push(new Paragraph({ children: [new PageBreak()] }));

/* ===== 7. Methodological weaknesses summary ===== */
body.push(H1("7. Methodological Weaknesses — Consolidated View"));
body.push(P("Section 3 records limitations indicator by indicator. The table below consolidates them into the recurring root causes, because each root cause has a single fix that resolves several indicators at once."));
body.push(SP(60));
body.push(tbl(
  ["Root cause", "Indicators affected", "Consequence"],
  [
    ["Derivative exposure derived from mark-to-market rather than notional or sensitivity", "KRI-04, KRI-12, KRI-13", "Leverage and derivative limits are very likely understated; the reported 1.07x leverage is not a reliable control reading."],
    ["Risk taxonomy driven by an uncontrolled free-text asset_class column", "KRI-04, KRI-07, KRI-09, KRI-11, KRI-13", "A single spelling variation silently changes five indicators with no error raised. Silent control failure."],
    ["Instrument-level rather than issuer-level aggregation, with no look-through", "KRI-05, KRI-06, KRI-11", "True issuer and counterparty concentration is systematically understated."],
    ["Inconsistent NAV versus GNAV normalisation", "Nine of thirteen indicators", "Limits are not mutually comparable once short positions exist."],
    ["Model parameters hardcoded in source instead of governed configuration", "KRI-04, KRI-08, KRI-09, KRI-10", "Stress and liquidity assumptions sit outside the approval and version control that thresholds enjoy."],
    ["Short and ungoverned lookback windows", "KRI-01, KRI-02, KRI-03", "Statistical estimates are too noisy to support hard limits; the lookback changes whenever the input file changes."],
    ["Allocation proxies presented as risk measures", "KRI-11, KRI-13", "An exposure percentage carries no information about credit quality or market sensitivity."],
    ["Point-in-time classification with no persistence rule or limit tiering", "All indicators", "Alert fatigue near limits; regulatory, prospectus and appetite breaches are indistinguishable."],
    ["Asset-side-only liquidity measurement", "KRI-08, KRI-09, KRI-10", "The fund's actual liquidity risk — the relationship between realisable assets and redeemable liabilities — is not measured at all."],
  ],
  [2900, 2300, 4438]
));

/* ===== 8. Gaps vs real world ===== */
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("8. Gaps Versus a Real-World KRI Monitoring Framework"));
body.push(P("The sections below describe capability that a production fund risk monitoring function requires and that the prototype does not currently have. Infrastructure items already acknowledged in SUPERVISOR_BRIEF.md Section 8 are omitted."));

body.push(H2("8.1 Governance and control framework"));
body.push(P("This is the largest gap, and it is not addressable by adding indicators. It concerns who is accountable, what authorises a limit, and whether the record would survive scrutiny."));
body.push(BULR([{ t: "Passive versus active breach classification. ", b: true }, { t: "A breach arising from market movement in a portfolio that was compliant when traded carries an obligation to correct without undue delay. A breach arising from a trade is a compliance incident requiring root-cause investigation and internal reporting. These are different processes with different owners and different reporting obligations, and the system has no concept of the distinction." }]));
body.push(BULR([{ t: "Three-tier limit framework. ", b: true }, { t: "Regulatory limits, prospectus limits and internal risk appetite triggers must be held as separate objects with separate escalation paths. A European fund context makes this concrete: UCITS issuer diversification rules and the related concentration caps, and the requirement to compute and disclose leverage under both the gross and commitment methods, are hard regulatory constraints. The prototype's single 20% concentration figure and single multiplier-based leverage figure do not map to any of them." }]));
body.push(BULR([{ t: "Limit change governance. ", b: true }, { t: "thresholds.json is read live and can be edited by anyone with file access. A limit framework requires an approval record, an effective date, a version history and a documented rationale for each value. The current design means yesterday's and today's reports can apply different limits with no trace of who changed them or why." }]));
body.push(BULR([{ t: "Authenticated identity and four-eyes control. ", b: true }, { t: "The actor on a state change is a free-text argument. Lifecycle transitions that carry accountability — in particular approval of a remediation plan and closure of a breach — require authenticated identity and a maker-checker separation so that the person who proposes an action is not the person who approves it." }]));
body.push(BULR([{ t: "Immutable audit trail. ", b: true }, { t: "The audit log must be append-only and tamper-evident, whether through database permissions, write-once storage or hash chaining. At present it is a freely editable table." }]));
body.push(BULR([{ t: "Service levels, ageing and an escalation ladder. ", b: true }, { t: "Due dates exist but are never enforced. A production process needs event ageing buckets, automatic overdue detection, and a defined escalation ladder from analyst to head of risk to the risk committee to the board, with each escalation itself recorded as an auditable event." }]));
body.push(BULR([{ t: "Model governance. ", b: true }, { t: "A model inventory, documented methodology, independent validation before production use, periodic revalidation, and backtesting evidence. The VaR model in particular cannot be used as a basis for a hard limit without a backtesting record." }]));
body.push(BULR([{ t: "Report review and attestation. ", b: true }, { t: "No record of who reviewed a given day's report, when, and whether they accepted it. The reviewer sign-off is normally the control that catches what the automated checks miss." }]));
body.push(BULR([{ t: "Regulatory and investor reporting consistency. ", b: true }, { t: "Figures presented internally should reconcile to those reported externally — periodic regulatory risk reporting, investor due diligence questionnaires, and fund documentation. There is currently no mapping between the internal indicator set and any external reporting template, which is how internal and external numbers drift apart." }]));
body.push(BULR([{ t: "Data lineage, retention and archival. ", b: true }, { t: "Immutable input snapshots, a defined retention period, and an archival policy for reports and the database. Related to D-09: without the input snapshot, lineage is broken at the first link." }]));

body.push(H2("8.2 Operational resilience"));
body.push(BULR([{ t: "Failure and absence alerting. ", b: true }, { t: "The highest-severity alert in a daily monitoring process is \"no report was produced today\". It must be generated by something outside the pipeline — a dead-man switch or heartbeat — because a pipeline that has failed cannot alert on its own failure. Writing stderr to a log file is not a control." }]));
body.push(BULR([{ t: "Graceful degradation. ", b: true }, { t: "Partial data should produce a report with the affected indicators explicitly marked unavailable, not an aborted run. Risk oversight with nine of thirteen indicators is far better than none, provided the gaps are visible." }]));
body.push(BULR([{ t: "Idempotent, safely repeatable runs. ", b: true }, { t: "Reruns and backfills are routine. They must be safe. See D-01 and D-02." }]));
body.push(BULR([{ t: "Multi-fund and multi-share-class operation. ", b: true }, { t: "The validation logic requires exactly one fund per run and thresholds are a single global file. A real function monitors dozens of sub-funds and share classes, each with limits drawn from its own fund documentation. Both the execution model and the configuration model need to become per-fund." }]));
body.push(BULR([{ t: "Alert fatigue management. ", b: true }, { t: "Deadbands, consecutive-day confirmation rules, suppression of known and accepted conditions, and a digest versus immediate-escalation distinction. A monitoring process that cries wolf is ignored, which converts a technical issue into a control failure." }]));
body.push(BULR([{ t: "Run service level monitoring. ", b: true }, { t: "Completion by a defined cut-off time, duration trending, and an alert when the run is late rather than only when it fails." }]));
body.push(BULR([{ t: "Concurrency safety. ", b: true }, { t: "Two simultaneous processes writing the history CSV will interleave, and SQLite will serialise or fail on write contention. Fine for a single scheduled job, unsafe the moment an analyst runs an ad-hoc recalculation during the batch window." }]));
body.push(BULR([{ t: "Reproducible environment. ", b: true }, { t: "Pinned dependency versions and a lockfile. Published risk figures must not change because a library was upgraded. See D-16." }]));

body.push(H2("8.3 Risk coverage"));
body.push(P("Ordered by materiality of the gap rather than by risk type."));

body.push(H3("Liability-side liquidity — the single largest coverage gap"));
body.push(P("The three liquidity indicators measure only how quickly assets can be realised. Fund liquidity risk is by definition a relationship between realisable assets and redeemable liabilities, and the liability side is entirely absent. A production framework requires:"));
body.push(BUL("Investor concentration: the largest investor and the top five investors as a share of NAV, and distinguishing discretionary from advisory and seeded capital.", 1));
body.push(BUL("Dealing terms: notice periods, dealing frequency, lock-ups and any investor-specific side letters.", 1));
body.push(BUL("A redemption coverage ratio: liquidity realisable within the notice period divided by a modelled redemption scenario, which is the indicator that actually answers whether the fund can meet redemptions.", 1));
body.push(BUL("Historical redemption distribution and a modelled severe-but-plausible redemption, rather than an implicit assumption that redemptions are zero.", 1));
body.push(BUL("Liquidity management tools and their trigger levels: swing pricing, redemption gates, side pockets, in-kind redemption, suspension.", 1));
body.push(BUL("Reverse liquidity stress testing: solving for the redemption level at which the fund can no longer meet obligations without disadvantaging remaining investors. Supervisory liquidity stress testing guidance expects this explicitly.", 1));

body.push(H3("Interest rate risk — entirely absent"));
body.push(P("The sample portfolio holds a ten-year government bond and an interest rate swap, and no indicator measures interest rate sensitivity in any form. There is no modified duration, no PV01 or DV01, no key-rate duration, no weighted average life and no curve-shape exposure. For any portfolio holding fixed income or rates derivatives this is a material blind spot, and it is not covered indirectly by VaR given the 21-day window."));

body.push(H3("Counterparty credit, collateral and margin"));
body.push(BUL("Counterparty identity is not even a field in the position schema."));
body.push(BUL("No uncollateralised mark-to-market exposure by counterparty and no counterparty concentration limit."));
body.push(BUL("No initial or variation margin tracking, no collateral haircut monitoring, no credit support annex threshold tracking."));
body.push(BUL("No margin-call liquidity linkage: a derivative margin call is a liquidity event, and the fact that the derivative and liquidity indicators do not speak to each other is how funds are surprised by collateral calls."));
body.push(BUL("No custodian or depositary concentration indicator."));

body.push(H3("Credit risk depth"));
body.push(P("As noted in KRI-11, the single credit indicator is an allocation bucket. Missing: exposure by rating band with a sub-investment-grade cap, weighted average credit rating, spread duration or CS01, issuer-level exposure, rating downgrade and migration monitoring, watchlist exposure, and probability-of-default or loss-given-default inputs. Sovereign exposure currently falls outside the credit indicator entirely because of the asset class labelling."));

body.push(H3("Currency risk"));
body.push(P("The position schema has no currency column, so the implicit assumption is that the entire portfolio and the NAV are denominated in a single currency. There is no currency exposure indicator, no hedge ratio monitoring and no hedge effectiveness measure. For a cross-border fund this is both a risk gap and a reporting gap."));

body.push(H3("Valuation risk"));
body.push(P("Illiquidity is measured; valuation uncertainty is not. Missing: share of NAV by fair value hierarchy level, valuation staleness in days since last independent valuation, the lag on general-partner reported valuations for private holdings, pricing source and pricing exception counts, and the share of NAV priced by a single source."));

body.push(H3("Risk attribution and decomposition"));
body.push(P("Every indicator reports a level. None reports a cause. A risk monitoring function needs component and marginal VaR by position and by risk factor, volatility contribution by holding, and factor exposures. Without decomposition, a VaR breach tells the committee that risk is too high but not which position to reduce, which is the only question the committee actually needs answered."));

body.push(H3("Benchmark-relative risk"));
body.push(P("No tracking error, beta, active share or relative sector and country exposure. For a benchmarked mandate, relative risk against the stated benchmark is typically the primary limit, not absolute risk."));

body.push(H3("Operational risk indicators"));
body.push(P("The project is named a KRI monitor, but a fund risk framework's key risk indicator set conventionally includes operational indicators alongside market and liquidity measures. None are present: NAV calculation error count and materiality, pricing exception count, reconciliation break count and ageing, failed and late trade settlements, cash overdraft and cash break incidents, breach count and average time to closure as a trend, late regulatory filings, and key-person or capacity indicators. These are often the indicators that a board actually reviews, and they are precisely the ones this system is already architecturally well suited to track given its event lifecycle model."));

body.push(H3("Other"));
body.push(BUL("Expected Shortfall or conditional VaR as the primary tail measure, given the demonstrated disagreement with VaR on this very portfolio."));
body.push(BUL("Correlation and diversification monitoring: average pairwise correlation, Herfindahl-Hirschman index, effective number of holdings."));
body.push(BUL("Sector, industry and geographic concentration."));
body.push(BUL("Sustainability risk indicators, where the fund has sustainability-related disclosure obligations."));
body.push(BUL("Risk-adjusted performance context: information ratio, and ex-ante versus ex-post risk comparison as a model validation input."));

/* ===== 9. Roadmap ===== */
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("9. Remediation Roadmap"));

body.push(H2("9.1 Prioritised actions"));
body.push(P("Priority is assigned on the basis of control risk, not implementation effort. P0 items are those where the system can currently produce a wrong answer, destroy an accountability record, or fail without anyone noticing."));
body.push(P("The four original P0 items have been completed, together with the breach-register defect found while building the test suite. They are retained in the table, marked Done, so the sequence of remediation remains visible. The next action on this list is the first P1 row.", { italics: true }));
body.push(SP(60));

const DONE = { t: "Done", c: GREEN, b: true };
const TODO = { t: "", c: undefined };

body.push(tbl(
  ["Pri", "Action", "Rationale", "Ref", "State"],
  [
    [{ t: "P0", c: RED, b: true }, "Introduce a test suite: golden-sample regression on all thirteen indicators, plus edge cases for short positions, zero ADV, single-holding portfolios, non-positive NAV, missing return series and duplicate dates.", "A silent arithmetic regression in a control system is an undetected control failure. This is the prerequisite for every other change on this list.", "D-05", DONE],
    [{ t: "P0", c: RED, b: true }, "Stop automatic closure of events in a human-owned state. Automatic clearing should record that the metric has returned to normal and move the event to a PENDING_CLOSURE state requiring explicit sign-off.", "Currently destroys the remediation and accountability record, and would also silently clear every open event after an upstream data incident.", "D-03", DONE],
    [{ t: "P0", c: RED, b: true }, "Make persistence idempotent: a unique key on fund, as-of date and metric, supersede-or-replace semantics for a rerun, and a collision-proof run identifier.", "Reruns and retries are routine operations and currently either duplicate data or crash.", "D-01, D-02", DONE],
    [{ t: "P0", c: RED, b: true }, "Enforce the lifecycle state machine with an explicit transition matrix, and replace the free-text actor with an authenticated identity.", "Without this the audit trail has no evidential value and the documented process is not actually implemented.", "D-04", DONE],
    [{ t: "P1", c: AMBER, b: true }, "Separate the breach register from the watch list in the workbook and in the data model.", "The sheet labelled Breach Log overstated the breach count by 150% on the sample portfolio, which makes it unusable as a regulatory record.", "D-17", DONE],
    [{ t: "P1", c: AMBER, b: true }, "Fix maximum drawdown to use the official NAV series; retain the constant-weight calculation as a separately named pro-forma indicator.", "Current figure is conceptually wrong and is presented to a committee as a realised statistic.", "KRI-02, D-06", TODO],
    [{ t: "P1", c: AMBER, b: true }, "Adopt a single documented exposure convention and apply it consistently; state explicitly for every indicator whether it is normalised by NAV or gross exposure.", "Nine indicators are currently inconsistent; the inconsistency is masked only by the long-only sample.", "3.1, D-08", TODO],
    [{ t: "P1", c: AMBER, b: true }, "Parameterise the VaR lookback with a governed minimum of 250 business days, add Expected Shortfall, and add a backtest.", "At present the indicator is a single observation, and Expected Shortfall disagrees with it on the limit verdict.", "KRI-01, D-07", TODO],
    [{ t: "P1", c: AMBER, b: true }, "Move derivative exposure onto notional, delta and PV01; implement gross and commitment leverage as two distinct indicators.", "Leverage is the limit most likely to be materially misstated today.", "KRI-12, KRI-13", TODO],
    [{ t: "P1", c: AMBER, b: true }, "Snapshot the return matrix per run and pin all dependency versions.", "Restores reproducibility of any published risk figure.", "D-09, D-16", TODO],
    [{ t: "P1", c: AMBER, b: true }, "Add failure and absence alerting independent of the pipeline, plus graceful degradation on partial data.", "A silent outage is currently indistinguishable from a clean day.", "D-10, D-11", TODO],
    [{ t: "P2", c: MIDBLUE, b: true }, "Externalise all model parameters to configuration; enforce a controlled vocabulary for asset class as a run-blocking data quality check.", "Removes the silent-failure path and brings stress assumptions under version control.", "KRI-04, KRI-07", TODO],
    [{ t: "P2", c: MIDBLUE, b: true }, "Add liability-side liquidity: investor concentration, dealing terms, a redemption coverage ratio and reverse stress testing.", "Highest-value single capability addition; converts the liquidity section from partial to meaningful.", "8.3", TODO],
    [{ t: "P2", c: MIDBLUE, b: true }, "Add interest rate risk indicators (duration, PV01, key-rate exposure) and deepen credit beyond an allocation bucket.", "Closes the two largest absent risk families given the portfolio's actual holdings.", "8.3", TODO],
    [{ t: "P2", c: MIDBLUE, b: true }, "Implement limit tiering (regulatory, prospectus, internal) and passive versus active breach classification.", "Determines the correct escalation path and remediation deadline for each breach type.", "3.6, 8.1", TODO],
    [{ t: "P2", c: MIDBLUE, b: true }, "Add deadbands and consecutive-day confirmation; add distance-to-limit, n-day change and consecutive-days-in-breach to the output.", "Reduces alert fatigue and makes the output genuinely early-warning rather than merely descriptive.", "3.6", TODO],
    [{ t: "P2", c: MIDBLUE, b: true }, "Add due-date enforcement, event ageing and an automatic escalation ladder.", "Due dates are calculated today but have no operational effect.", "5", TODO],
    [{ t: "P3", c: "595959", b: true }, "Multi-fund and multi-share-class execution with per-fund limit sets.", "Required before the tool can serve more than a single demonstration portfolio.", "8.2", TODO],
    [{ t: "P3", c: "595959", b: true }, "Risk attribution: component and marginal VaR, volatility contribution by holding.", "Answers the question a risk committee actually asks when a limit is breached.", "8.3", TODO],
    [{ t: "P3", c: "595959", b: true }, "Counterparty, collateral and margin monitoring, with a margin-call liquidity linkage.", "Connects the derivative and liquidity indicator sets.", "8.3", TODO],
    [{ t: "P3", c: "595959", b: true }, "Operational risk indicator set (NAV errors, pricing exceptions, reconciliation breaks, breach ageing trend).", "The existing event lifecycle architecture is already well suited to these, so marginal cost is low.", "8.3", TODO],
    [{ t: "P3", c: "595959", b: true }, "Issuer and ultimate-parent aggregation with fund look-through; currency and valuation risk indicators; benchmark-relative risk.", "Completes the coverage of a conventional fund risk indicator set.", "8.3", TODO],
  ],
  [500, 3100, 3300, 1738, 1000]
));

body.push(H2("9.2 Suggested sequencing"));
body.push(P("The four P0 items were mutually independent and individually small, and have been completed. They were taken first because every remaining item changes calculation logic, and none of those changes can be made safely without the test suite in place. Stage 2 is now the active stage."));
body.push(SP(60));
body.push(tbl(
  ["Stage", "Content", "Exit criterion", "State"],
  [
    ["Stage 1 — Make it trustworthy", "The four P0 items: test suite, safe event closure, idempotent persistence, enforced state machine with authenticated actors.", "Met. The pipeline reruns safely, 107 regression tests run from a clean clone, and no event in a human-owned state can be closed without a named person and a recorded rationale.", { t: "Complete", c: GREEN, b: true }],
    ["Stage 2 — Make it correct", "P1 items: drawdown, exposure convention, VaR window and Expected Shortfall, derivative exposure basis, input snapshotting, failure alerting.", "Every published figure is reproducible, methodologically defensible, and documented in this methodology reference.", { t: "Active", c: AMBER, b: true }],
    ["Stage 3 — Make it operable", "P2 items: configuration governance, liability-side liquidity, rates and credit depth, limit tiering, alert fatigue controls, due-date enforcement.", "Suitable for a controlled pilot on live data with a named risk owner and a defined escalation path.", { t: "Not started", c: "595959" }],
    ["Stage 4 — Make it complete", "P3 items: multi-fund, risk attribution, counterparty and collateral, operational indicators, look-through and relative risk.", "Coverage comparable to a conventional fund risk indicator framework.", { t: "Not started", c: "595959" }],
  ],
  [1900, 3700, 2838, 1200]
));

body.push(H2("9.3 Closing assessment"));
body.push(P("The prototype already implements the correct control loop and, unusually for a self-built tool, already treats a threshold exception as an accountable event rather than a line in a report. That design instinct is the hard part and it is present."));
body.push(P("What is missing falls into three distinct categories, and they should not be conflated. The defects in Section 6 are engineering faults with known fixes. The weaknesses in Section 7 are methodological simplifications that require risk modelling decisions and, in several cases, additional reference data. The gaps in Section 8 are framework capability, much of which concerns governance rather than code and therefore requires decisions about accountability, approval and record-keeping that no amount of development will substitute for."));
body.push(P("As a demonstration of how daily fund risk monitoring can move from static reporting to a traceable control process, the prototype is already convincing. At the time of the original review the two items that mattered most were the absence of any test coverage and the automatic closure of events under human investigation: the first meant an error could not be detected, the second meant the accountability record the project was built to create could be destroyed by a market movement. Both have since been fixed, together with the idempotency and state-machine defects, and each fix is held in place by regression tests."));
body.push(P("That changes the project's standing as a control, not the standing of its numbers. The workflow can now be relied on to behave identically twice, to refuse an illegal state change, and to refuse to close a record on a person's behalf. It cannot yet be relied on to produce a VaR figure fit to put in front of a committee: the lookback is twenty-one observations rather than a governed window, the drawdown is a constant-weight backcast presented as a realised statistic, and the exposure denominator is inconsistent in a way the long-only sample conceals. That work is Stage 2, and it is the difference between a defensible control process and a defensible risk number. The prototype now has the first of the two."));

/* ===== Appendix ===== */
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("Appendix A — Indicator Reference Table"));
body.push(P("All values computed from the bundled sample portfolio: fund KRI_FUND, as-of date 31 December 2024, NAV 10,000,000, eight holdings, twenty-one return observations."));
body.push(SP(60));
body.push(tbl(
  ["ID", "Indicator", "Formula (condensed)", "Warn", "Limit", "Value", "Status"],
  [
    ["01", "VaR 95% 1-day", "|pctile(R,5)|", "2.00%", "2.50%", "1.89%", { t: "OK", c: GREEN, b: true }],
    ["02", "Max drawdown", "|min(V/cummax(V)-1)|", "6.00%", "8.00%", "6.40%", { t: "WATCH", c: AMBER, b: true }],
    ["03", "Volatility 20d", "sd(R20)x sqrt(252)", "18.00%", "25.00%", "14.61%", { t: "OK", c: GREEN, b: true }],
    ["04", "Equity shock -10%", "0.10x(wEq+0.5xwDeriv)", "4.00%", "6.00%", "5.58%", { t: "WATCH", c: AMBER, b: true }],
    ["05", "Concentration", "max(|MV|/GNAV)", "15.00%", "20.00%", "22.00%", { t: "BREACH", c: RED, b: true }],
    ["06", "Top-5 concentration", "sum top5 |MV|/GNAV", "65.00%", "75.00%", "83.00%", { t: "BREACH", c: RED, b: true }],
    ["07", "Largest asset class", "max class |MV|/GNAV", "45.00%", "55.00%", "54.00%", { t: "WATCH", c: AMBER, b: true }],
    ["08", "Liquidity ratio 5d", "sum(L<=5)|MV|/GNAV", "40.00%", "30.00%", "87.50%", { t: "OK", c: GREEN, b: true }],
    ["09", "Stressed liquidity 5d", "0.75xmin(|MV|,ADVx1)/NAV", "25.00%", "15.00%", "65.63%", { t: "OK", c: GREEN, b: true }],
    ["10", "Illiquid ratio", "sum(L>10)|MV|/GNAV", "20.00%", "30.00%", "9.00%", { t: "OK", c: GREEN, b: true }],
    ["11", "Credit exposure", "sum Credit |MV|/GNAV", "20.00%", "30.00%", "13.00%", { t: "OK", c: GREEN, b: true }],
    ["12", "Gross leverage", "sum(|MV|x|m|)/NAV", "1.25x", "1.50x", "1.07x", { t: "OK", c: GREEN, b: true }],
    ["13", "Derivative exposure", "sum Deriv GE/NAV", "20.00%", "30.00%", "10.50%", { t: "OK", c: GREEN, b: true }],
  ],
  [500, 1900, 2538, 900, 900, 900, 2000]
));
body.push(SP(160));
body.push(P("Not currently calculated but computed during this review for comparison: Expected Shortfall at 95% equals 2.5425%, which exceeds the 2.50% hard limit applied to VaR. See KRI-01.", { italics: true }));
body.push(SP(100));
body.push(P("Note on KRI-09 in the table above: ADV x 1 denotes the five-day capacity term ADV x 0.20 x 5. See Section 3.4 for the full expression.", { italics: true, size: 18 }));

/* ---------- assemble ---------- */
const doc = new Document({
  creator: "Risk Management",
  title: "Fund KRI Monitor — Technical Review",
  description: "Calculation methodology, verified defects, gaps and remediation roadmap",
  styles: {
    default: {
      document: { run: { font: "Calibri", size: 21 } },
      heading1: { run: { font: "Calibri", size: 32, bold: true, color: NAVY }, paragraph: { spacing: { before: 360, after: 160 } } },
      heading2: { run: { font: "Calibri", size: 26, bold: true, color: MIDBLUE }, paragraph: { spacing: { before: 280, after: 120 } } },
      heading3: { run: { font: "Calibri", size: 22, bold: true, color: "404040" }, paragraph: { spacing: { before: 200, after: 80 } } },
    },
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 400, hanging: 220 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 760, hanging: 220 } } } },
      ],
    }],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 },
      },
    },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("/Users/leli/Desktop/test/fund_kri_monitor/Fund_KRI_Monitor_Technical_Review.docx", buf);
  console.log("written:", buf.length, "bytes");
});
