# The data behind the claims

Every public number in this repository is a measurement on some set of agreements, and each set has its
own size, source and licence. This file is the audit of those sets, produced by
`backend/scripts/data_audit.py` from the manifests in the tree, the store on this machine, and the
measurement records that live outside git. It exists so that a claim like "verified 1,233 of 1,351
quoted passages" or "37 of 44 goldens" is read with its denominator, and so that nobody, including the
author, adds the sets together into a number that means nothing.

What the script does not do: it does not copy any measured result from the other documents. The
results stay where they were recorded (`docs/GOLDENS.md`, `docs/CUAD.md`, `docs/RETRIEVAL.md`,
`docs/BATCH.md`, `docs/FAMILIES.md`, `docs/PARSER-COMPARISON.md`, `docs/SCALE.md`,
`docs/VALIDATION.md`), each with the command that regenerates it. This file only says what the
measurements were made on.

```bash
cd backend
.venv/Scripts/python scripts/data_audit.py            # print the audit
.venv/Scripts/python scripts/data_audit.py --write    # refresh the block below
```

Roles: **evaluation** is a corpus, a label set or the golden document; **fixture** is an input a test or
a browser flow uses; **runtime** is bytes a person uploaded through the API, which measured nothing.
Bytes can hold more than one role (the bundled sample is the golden document, the browser flows' input
and CP01 of the public corpus). Licences come from the corpus provenance file in `ivo-experiments`
(`corpus_sources.csv`), the CUAD archive's `SOURCE.txt`, and the sample's attribution; anything else
reads "not recorded".

## The audit, as last run

Run on 2026-09-30 against this machine's store after the Phase 1 proof (`docs/DEMO-PROOF.md`).

<!-- data-audit:start -->

Store audited: `backend\data\workbench.db`

Distinct agreements known to this repository, by SHA-256: **87**.

### evaluation (80)

| sha256 | names | source | licence | readings | runs | measurements |
|---|---|---|---|---|---|---|
| `6cdfab95eb5b30c0…` | 01-2themartcominc-19990826-10-12g-ex-10-10-6700288-ex-10-10-co-.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 17 | CUAD-30 clause measurement; batch 'cuad-30' |
| `c757bb1d60075511…` | 01-adianutrition-inc-04-01-2005-ex-10-d2-reseller-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `3c70a981a2107097…` | 02-alamogordofinancialcorp-12-16-1999-ex-1-agency-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 15 | CUAD-30 clause measurement; batch 'cuad-30' |
| `800a8e3e69cecab8…` | 02-americasshoppingmallinc-12-10-1999-ex-10-2-site-development-.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `28f64048e5b3ba33…` | 03-antares-pharma-inc-manufacturing-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `f8634e3d4296d325…` | 03-atmosenergycorp-11-22-2002-ex-10-17-transportation-service-a.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 15 | CUAD-30 clause measurement; batch 'cuad-30' |
| `5cb5b5a5e08db4d1…` | 04-audibleinc-20001113-10-q-ex-10-32-2599586-ex-10-32-co-brandi.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `f8438559b293e822…` | 04-bicycletherapeuticsplc-03-10-2020-ex-10-11-service-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `1e6bf0ff8fcb0744…` | 05-blueflyinc-03-27-2002-ex-10-27-e-business-hosting-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `61a7d17bc4cba453…` | 05-borrowmoneycom-inc-06-11-2020-ex-10-1-joint-venture-agreemen.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `9620281e798e7635…` | 06-ccaindustriesinc-04-14-2014-ex-10-1-outsourcing-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `a3c62071e79c5a3c…` | 06-chipmostechnologiesbermudaltd-04-18-2016-ex-4-72-strategic-a.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `4a3e5cdd6270a41d…` | 07-ccrealestateincomefundadv-20181205-pos-8c-ex-99-h-3-11447739.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `e6370745e927c118…` | 07-coherusbiosciencesinc-20200227-10-k-ex-10-29-12021376-ex-10-.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `97fe5dcb9450133b…` | 08-deltathreeinc-19991102-s-1a-ex-10-19-6227850-ex-10-19-co-bra.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `bae9c2a33cdb12e3…` | 08-drivendeliveries-inc-05-22-2020-ex-10-4-consulting-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `c94be1a4bdea0863…` | 09-ebixinc-20010515-10-q-ex-10-3-4049767-ex-10-3-co-branding-ag.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `5b46b0a384a0ae62…` | 09-energyxxiltd-05-08-2015-ex-10-13-transportation-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `d83398bc5b3ef6d6…` | 10-emmiscommunicationscorp-20191125-8-k-ex-10-6-11906433-ex-10-.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `f9db7b25f0fd035c…` | 10-ftenetworks-inc-02-18-2016-ex-99-4-strategic-alliance-agreem.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `c9c939c124076c8a…` | 11-gainscoinc-01-21-2010-ex-10-41-sponsorship-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `cceff2701a7aa063…` | 11-gsvinc-05-15-1998-ex-10-sponsorship-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `ab313de5385c0998…` | 12-glumobileinc-20070319-s-1a-ex-10-09-436630-ex-10-09-content-.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `47ee42edcfd94c66…` | 12-hc2holdings-inc-05-14-2020-ex-10-1-cooperation-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `58a3602dd88ac590…` | 13-herimports-20161018-8-ka-ex-10-14-9765707-ex-10-14-maintenan.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `98ba454bb3ccef1b…` | 13-hpilholding-01-07-2015-ex-99-1-cooperation-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `7b93d296763d8c74…` | 14-impcotechnologiesinc-04-15-2003-ex-10-65-joint-venture-agree.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `1aa2574ca312a72c…` | 14-iovancebiotherapeutics-inc-08-03-2017-ex-10-1-strategic-alli.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `bfb7b9610645dde4…` | 15-imperialgardenresortinc-20161028-drs-on-f-1-ex-10-13-9963189.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `4db68fb78e12cf32…` | 15-invendacorp-20000828-s-1a-ex-10-2-2588206-ex-10-2-co-brandin.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `70d818aaac809a4e…` | 16-knowlabs-inc-08-15-2005-ex-10-intellectual-property-agreemen.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `66048676c514d1e7…` | 16-lightbridgecorp-11-23-2015-ex-10-26-strategic-alliance-agree.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `58078cc191465e41…` | 17-legacyeducationallianceinc-20141110-8-k-ex-10-9-8828866-ex-1.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `f9cfca1abe0d53c6…` | 17-lohacompanyltd-20191209-f-1-ex-10-16-11917878-ex-10-16-suppl.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `7aa6582007f2f953…` | 18-meetgroup-inc-06-29-2017-ex-10-1-cooperation-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `6f93ddd1129f5199…` | 18-mossimoinc-04-14-2000-ex-10-14-endorsement-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `23c6922eb12fba24…` | 19-midwestenergyemissionscorp-20080604-8-k-ex-10-2-3093976-ex-1.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `b3db6d72f9b7e01a…` | 19-neomediatechnologiesinc-12-15-2005-ex-16-1-distributor-agree.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `4faa34333f1d42ec…` | 20-nmfslfiinc-20200115-10-12ga-ex-10-5-11946987-ex-10-5-tradema.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `ed8ec45674420e7e…` | 20-novointegratedsciences-inc-12-23-2019-ex-10-1-joint-venture-.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `579818d20eb50a9c…` | 21-operaltd-04-30-2020-ex-4-14-service-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `874eb07ae3632c67…` | 21-paxmedica-inc-07-02-2020-ex-10-12-master-service-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `9c66eef9725257be…` | 22-pareteumcorp-20081001-8-k-ex-99-1-2654808-ex-99-1-hosting-ag.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `915146be0c3ac149…` | 22-prolonginternationalcorp-03-23-1998-ex-10-16-sponsorship-agr.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `db39d6c284788dfd…` | 23-phoenixnewmedialtd-20110421-f-1-ex-10-17-6958322-ex-10-17-co.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `c1c3668fe4a3a445…` | 23-quaker-chemical-corporation-non-competition-and-non-solicita.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `a98e1239e03d1dfb…` | 24-raesystemsinc-20001114-10-q-ex-10-57-2631790-ex-10-57-co-bra.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `633730271ed5a6b4…` | 24-remarkholdingsinc-20081114-10-q-ex-10-24-2895649-ex-10-24-co.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `c56352505b46b56b…` | 25-separateaccountiiofagl-05-02-2011-ex-99-j-4-unconditional-ca.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `0c1d630fd900445b…` | 25-sparklingspringwaterholdingsltd-07-03-2002-ex-10-13-software.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `78d91abf7c1efc2a…` | 26-scansourceinc-20190822-10-k-ex-10-38-11793958-ex-10-38-distr.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `58356a12396d1fac…` | 26-stwresourcesholdingcorp-08-06-2014-ex-10-1-cooperation-agree.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `3d9aff615a747ad4…` | 27-sonos-inc-manufacturing-agreement.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `058d89037c36c9dc…` | 27-talcottresolutionlifeinsuranceco-separateaccounttwelve-04-30.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `1c475f59db3b10b7…` | 28-tomonlineinc-20060501-20-f-ex-4-46-749700-ex-4-46-co-brandin.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `36724bd21fa87d10…` | 28-trizettogroupinc-08-18-1999-ex-10-17-technical-infrastructur.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `42ae613e5bb22f1c…` | 29-usioinc-20040428-sb-2-ex-10-11-1723988-ex-10-11-affiliate-ag.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `4b2cb71fad30b513…` | 29-vertexenergyinc-08-14-2014-ex-10-24-operation-and-maintenanc.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `480cfbb8c3b84fd4…` | 30-vertexenergyinc-20200113-8-k-ex-10-1-11943624-ex-10-1-market.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | v4 | 7 | CUAD-30 clause measurement; batch 'cuad-30' |
| `2e450b492547179d…` | 30-warningmanagementservicesinc-12-10-1999-ex-10-endorsement-ag.txt | CUAD v1 (SEC exhibit) | CC BY 4.0 (CUAD v1, The Atticus Project) | not in the store | 0 | SkillOpt (disjoint CUAD contracts) |
| `cb72dad74b3af676…` | CP01.docx, Cloud Service Agreement (Common Paper).docx, cloud-service-agreement.docx | Common Paper (CP01); bundled sample (Common Paper Cloud Service Agreement v2.1) | CC BY 4.0 | unversioned, unversioned, unversioned, unversioned, unversioned, unversioned, v2, v3, v4 | 403 | batch 'public-corpus'; browser flows (replayed answers); document families (hand labels); golden set; interface performance; load envelope; parser tournament; public corpus (batch, families, parser tournament) |
| `d8cc13f589096d1b…` | CP02.docx | Common Paper (CP02) | CC BY 4.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `18e07001c3ebfc74…` | CP03.docx | Common Paper (CP03) | CC BY 4.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `cb35f3cc70cb6d24…` | CP04.docx | Common Paper (CP04) | CC BY 4.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `c711cef731218c16…` | CP05.docx | Common Paper (CP05) | CC BY 4.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `ae3023105755ecd9…` | CP06.docx | Common Paper (CP06) | CC BY 4.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `2b85bb4cd1a105da…` | CP07.docx | Common Paper (CP07) | CC BY 4.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `0a073e0e20878117…` | CP08.docx | Common Paper (CP08) | CC BY 4.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `43c7e8b70daf2177…` | UK01.docx | UK Cabinet Office (gov.uk) (UK01) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `49f6edd53f0d7987…` | UK02.docx | UK Cabinet Office (gov.uk) (UK02) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `c3d056e64cac0fe1…` | UK03.docx | UK Cabinet Office (gov.uk) (UK03) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `88c177fe3a74dec5…` | UK04.docx | UK Cabinet Office (gov.uk) (UK04) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `918e9959d5fa4a0f…` | UK05.docx | UK Cabinet Office (gov.uk) (UK05) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `3a55ae9241564f0e…` | UK06.docx | UK Cabinet Office (gov.uk) (UK06) | OGL v3.0 | unversioned, v3, v4 | 4 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `63fb4ff02ea47e9d…` | UK07.docx | UK Intellectual Property Office (gov.uk) (UK07) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `a2af977adec01597…` | UK08.docx | UK Department for Education (gov.uk) (UK08) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `ce3477f51ea03809…` | X01.docx | UK Information Commissioner's Office (ico.org.uk) (X01) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `81fa7eb166eba183…` | X02.docx | UK Information Commissioner's Office (ico.org.uk) (X02) | OGL v3.0 | unversioned, v3, v4 | 4 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `67758746efdd50fa…` | X04.docx | Scottish Government (gov.scot) (X04) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |
| `d5eddaaddd083569…` | X05.docx | Scottish Government (gov.scot) (X05) | OGL v3.0 | v3, v4 | 3 | batch 'public-corpus'; document families (hand labels); parser tournament; public corpus (batch, families, parser tournament) |

### fixture (3)

| sha256 | names | source | licence | readings | runs | measurements |
|---|---|---|---|---|---|---|
| `cb72dad74b3af676…` | CP01.docx, Cloud Service Agreement (Common Paper).docx, cloud-service-agreement.docx | Common Paper (CP01); bundled sample (Common Paper Cloud Service Agreement v2.1) | CC BY 4.0 | unversioned, unversioned, unversioned, unversioned, unversioned, unversioned, v2, v3, v4 | 403 | batch 'public-corpus'; browser flows (replayed answers); document families (hand labels); golden set; interface performance; load envelope; parser tournament; public corpus (batch, families, parser tournament) |
| `60f9c7eaa5eddc9c…` | agreement.txt (tests.support.CONTRACT) | synthetic test contract | the repository's own | not in the store | 0 | backend tests |
| `c61812563bbee7b2…` | services-agreement.pdf | test fixture (printed from Chrome) | the repository's own | not in the store | 0 | backend tests |

### runtime (5)

| sha256 | names | source | licence | readings | runs | measurements |
|---|---|---|---|---|---|---|
| `d510d1d71a7b6629…` | MTI-Reseller-Agreement.docx | uploaded through the API | not recorded | v4 | 1 | none |
| `effe1fee8dee4160…` | cloud-service-agreement.pdf | uploaded through the API | not recorded | unversioned, unversioned, unversioned | 0 | none |
| `7b4ab0a901c9746e…` | large-services-agreement.txt | uploaded through the API | not recorded | v3 | 0 | none |
| `a60d28ecb4d677b9…` | redlined-msa.docx | uploaded through the API | not recorded | v2 | 0 | none |
| `946bad8aae9e111a…` | review-memo-6939b40558314bea.docx | uploaded through the API | not recorded | v4 | 0 | none |

### Denominators, each its own

| What | Number | Counted from |
|---|---|---|
| golden questions | 44 | app/goldens/set.json, on one document (the sample) |
| public corpus agreements with provenance | 20 | ivo-experiments\experiments\b1-word-structure\corpus_sources.csv |
| cuad-30.json contracts | 30 | app/batch/corpora/cuad-30.json |
| cuad-skillopt.json contracts | 30 | app/batch/corpora/cuad-skillopt.json |
| CUAD-30 questions (one per category) | 7 | app/batch/tasks/cuad-clauses.json |
| batch fields over the public corpus | 3 | app/batch/tasks/core-fields.json |
| hand-labelled documents for families | 20 | app/families/labels.json |
| recorded model answers replayed by the browser flows | 3 | e2e/replay.json, all on the sample |
| browser flows | 20 | e2e/*.spec.ts |
| hand mutants | 24 | scripts/mutate_by_hand.py |
| distinct agreements in batch 'cuad-30' | 30 | the store's batch_items |
| distinct agreements in batch 'public-corpus' | 20 | the store's batch_items |
| evidence spans in the store (a verifier replay's population) | 1351 (1233 verified) | the store's evidence_spans, at the time of the audit |
| runs in the store | 699 | the store's runs, at the time of the audit |
| documents in the parser tournament's baseline record | 21 | data/tournament/current.json (not in git) |
| admission measurement records | 1 | data/logs/admission-*.json (not in git) |
| load envelope records | 2 | data/logs/load-envelope-*.json (not in git) |

### The same bytes, more than once

- 21 agreements are stored as more than one reading (unversioned, v2, v3, v4): one set of bytes, one row per reader version, kept because finished runs read each of them
- `cb72dad74b3af676…` is known under 3 names: CP01.docx, Cloud Service Agreement (Common Paper).docx, cloud-service-agreement.docx

### Not audited here

- the Phase 1 fixture (docs/DEMO-PROOF.md) is a CUAD contract rendered as a DOCX by experiments/demo_proof/make_fixture.py; its bytes are in the store only where the proof was run

### The strongest claim these records allow

Every measurement in this repository was made on one of 80 evaluation agreements, 80 of them under a recorded licence (CC BY 4.0 or OGL v3.0), and each measurement has its own denominator in the table above: the golden set is questions about one contract, CUAD-30 is thirty text files against experts' spans, the batch and the families are the twenty-document public corpus, and the verifier replay is a count of spans, not of contracts. These numbers are not added together, because the sets overlap (the bundled sample is CP01 of the corpus) and because a span, a question and a contract are not the same unit. 5 further agreements in the store were uploaded through the API by a person and measured nothing; they are listed so that no count above quietly includes them.

<!-- data-audit:end -->

## Reading it

- The five runtime agreements are the builder's own uploads while building (a PDF print of the sample,
  a redline fixture, the 2,001-section performance fixture, a generated memo uploaded back, and the
  Phase 1 contract); none of them is behind a number in any document, and `docs/DEMO-PROOF.md` names the
  last one as a proof, not a measurement.
- Eleven readings carry no reader version: they were stored before reader versioning existed
  (2026-09-28) and are kept because finished runs read them. They are the same bytes as versioned rows
  beside them.
- The CUAD sets are text files, not Word files, and the SkillOpt thirty are disjoint from CUAD-30 by
  construction (`docs/SKILLOPT.md`). Neither was ever read by the interface's upload path except through
  the batch runner.
- The public corpus of twenty is eight Common Paper agreements (CC BY 4.0) and twelve UK government
  documents (OGL v3.0); the pilot corpus that fed the families labels overlaps it, and the labels file
  identifies documents by sha256 prefix so that the same bytes under another name still count.
