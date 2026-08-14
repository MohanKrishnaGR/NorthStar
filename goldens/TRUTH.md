# T1 Truth Sheet

Human-readable expectations for the Tier-1 persona corpus (`goldens/t1/`).
The machine twin is `tests/test_golden_t1.py` — one test per persona, named
after it, so a failure names the broken mechanism. Pinned bytes live in
`goldens/expected/` (regenerate with the two commands in that test's header
and review the diff by eye before committing).

Run pin: `--as-of 2026-08`. Expected: **28 profiles** (default config),
**24** under `recruiter_view` (4 excluded: Lena Novak and Priya Patel have no
email, the gossip profile has no name, Noor Zaidi has neither).

Fixture touches from RESUME_PLAN (2026-08-14): P01's resume gained a skills
*table* (Terraform | Airflow — DOCX tables were previously invisible), P07's
resume gained an education line, P18's resume first line became pipe-separated
("Tomas Eder | Frontend Lead") — each existing persona's mechanism unchanged,
one new assert each.

| Persona | Mechanism | Expectation (and why) |
|---|---|---|
| P01 Avery Stone | ceiling anchor; all 6 source types | One 7-record cluster (CSV + ATS ×2 incl. exact duplicate + notes + resume + GitHub + LinkedIn), joined by email and profile-URL link keys. `years=5.6` (2021-02→as-of). GitHub `go` skill present at 0.45 — *below* every explicitly-claimed skill (derived reliability). Duplicate ATS entry corroborates nothing extra (once-per-source rule). |
| P02 Bina Rao | plus-tag / gmail-dot / googlemail keying | 3 email variants key to one `binarao@gmail.com` identity → 1 cluster; all 3 originals preserved; `emails[0]` is an ATS variant (trust-ordered, tie broken by value). Title "Senior Data Analyst" (ATS beats CSV). |
| P03 Núñez, Carlos | name reorder + NFC-vs-NFD accents | CSV "Núñez, Carlos" (NFC) and resume "Carlos Núñez" (NFD bytes) **merge** — accent-insensitive token compat. Winner "Núñez, Carlos" (CSV 0.85 > resume 0.70); the other is an alternative. |
| P04 Devi Iyer | phone pass-2 via cluster country | CSV national phone + ATS *numeric JSON* phone both unresolvable at pass 1 → cluster country IN (ATS location) resolves both to `+919812345678`, which then corroborates itself across two sources. |
| P04b Farid Khan | pass-2 dead end | National phone, **no** location anywhere → `phones: []`, raw preserved, reason `no_region_context`. Never a silent +1/+91. |
| P05 Grace Obi | true conflicts | Name conflict ("Grace N. Obi" CSV vs "Grace Obi" ATS): ATS wins, CSV kept as alternative, and `full_name` confidence < P01's (support penalty). Skills arrive as the string `"SQL, Python"` — split, not char-iterated. "Helios Retail" vs "Helios Retail Group" stay two entries (companies differ — append, don't fuse). |
| P06 Hana Suzuki | promotion + overlap + link-key join | LinkedIn fixture joins via profile-URL key (no email in it). Manager and Senior stints stay separate entries; the overlapping Nova Labs advisory doesn't double-count: `years=6.7` (80 contiguous months). |
| P07 Ishaan Verma | year-only + ambiguous dates; CV heading | "Curriculum Vitae" first line correctly declined as a name (name comes from the notes label). Quanta "2019 - 2021" renders year-only; Meridian `03/04/2021` keeps the year, drops the ambiguous month. `years=3.0` (Meridian nested inside Quanta). |
| P08 Jorge Silva | stated-vs-derived years | Claims 15y; ranges derive 5.3y → derived wins, "15" recorded as alternative, confidence penalized by the disagreement. |
| P09 Kiran Patel ×2 | negative control: distinct strong keys | Same name + company, different emails → **two** profiles. Soft key never fires when strong keys exist. |
| P10 Lena Novak ×2 | the soft-key boundary, kept visible | No strong keys, same name + company → soft key **merges** them. This is the documented false-merge boundary — in the gold deliberately, not hidden. Null-marker cells ("—") contribute nothing. |
| P11 Sam Ortiz / Dana Kim | shared referral inbox | Same email, incompatible names → union refused (`suspect_shared_identifier`), two profiles, and **distinct candidate_ids** (the contested email is excluded from id seeding — the collision this corpus caught at design time). |
| P12 Omar / Petra | switchboard phone | Same office phone, different people → refusal via the *phone* key kind; both keep the number in their profiles (evidence stays; only the union is refused). |
| P13 Casey Chen chain | transitive positive | CSV (email) – ATS (email+phone) – notes (phone only, no name) → one 3-record cluster; notes skills (kafka, kubernetes) attach. Name winner is ATS's "C. Chen" (trust ordering — initials win over the fuller CSV name; policy, visible here on purpose). |
| P13b Blair / "Priya Patel" | broken chain | Same shape, but the notes file names a different person → phone union refused; Priya Patel becomes her own profile. |
| P14 gossip file | multi-identity guard | 3 emails in one notes file → `multi_identity_source`, attaches to no cluster, its quasi-profile (name null, 3 emails) gets a record-seeded id that collides with no one. |
| P15 Noor Zaidi | honest floor | Notes-only, no contact keys → singleton, minimal profile; excluded under `recruiter_view` (required email missing). |
| P16 田中太郎 / 田中 太郎 | CJK spacing limitation | Same email, spaced vs unspaced CJK name → token predicate sees no overlap → refusal → **two profiles** (false split, recoverable; DESIGN §5 row 19). Distinct ids via contested-key fallback to name+company. |
| P17 Rhea Hoardley | skills gauntlet | Aliases fold (ReactJS/react.js → react once; Golang → go; K8s → kubernetes; TS → typescript); "MS Office" kept `canonical:false`; GitHub `yaml`/`jupyter notebook` at 0.45 below every ATS skill; bait prose adds no "spring"/"rest". GitHub `name: null` promotes nothing. |
| P18 Tomas Eder | URL conflicts | Same-slug-with-tracking-params corroborates (match key ignores query); the alt-slug from notes loses and is preserved as an alternative; github + portfolio links captured. |
| P19 Uma Reddy | degenerate dates | Future-dated current job (2030→) and inverted range (2022-05→2021-01) are dropped from the years sum with named reasons; all 3 entries still emitted; `years=0.1` (the one sane month). |
| P20 Renée Fontaine | encoding fallback | cp1252 bytes decode via the deterministic fallback; name and "Café Lumière" keep their accents; `+33` phone normalizes at pass 1. |
| P21 Wale Adeyemi | the real-PDF path | A hand-rolled single-column PDF (tools `minimal_pdf`) through pdfplumber: pipe-split contact-line name, block-form experience ("Harmattan Cloud -- Platform Engineer" over a pure range line → 2022-03→present, `years=4.5`), education grammar ("B.Sc in Computer Science, University of Lagos, 2016"). Three mechanisms, three separate test functions. |

**Aggregate asserts:** all candidate_ids unique; exactly 4 refusals (2 email,
2 phone kinds); `unparseable` reasons exactly {no_region_context,
inverted_date_range, future_dated_range}; profile counts 27/23.
