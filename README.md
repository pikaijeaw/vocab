# vocab

Vocabulary lists with Thai meanings + one local study dashboard (flashcards, quiz, browse, word graph).

| Subject | CSV | Words | Update script |
|---|---|---|---|
| Chinese HSK 1–6 | `hsk_vocab_level1-6.csv` | ~7,800 | `scripts/update_hsk.py` |
| English TOEIC | `toeic_vocab.csv` | ~4,050 | `scripts/update_toeic.py` |

## Dashboard
`python3 dashboard/serve.py` → http://127.0.0.1:5005/ (HSK) and http://127.0.0.1:5005/toeic.html (TOEIC). Switch subjects with the HSK / TOEIC toggle at the top right. Progress is kept in the browser (localStorage), separately per subject.

## Auto-update
`scripts/sync_all.sh` runs both update scripts (on this server: systemd `vocab-sync.timer`, 1st and 15th of every month). Each script re-downloads its sources, adds missing words, re-checks and fixes existing rows, rebuilds the dashboard data file, and commits + pushes only if something changed. Options: `--dry-run`, `--no-push`.

## HSK CSV columns
`hsk2_old_level, hsk3_new_level, hanzi, traditional, pinyin, thai, pos, meaning, hsk3_2026_level, thai_auto`
- Source: [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) (MIT).
- `thai_auto=1` = Thai machine-translated.

## TOEIC CSV columns
`band, list, rank, word, ipa, thai, pos, meaning, forms, thai_auto`
- `list` = `TSL` (TOEIC Service List — TOEIC-specific words) or `NGSL` (New General Service List — most frequent general English words). Together ≈ 99% of the words in TOEIC tests.
- `band` 1–3 = general words by frequency (1k / 2k / 3k), 4–6 = TOEIC core words by frequency (A / B / C).
- `thai_auto=1` = the first Thai sense is machine-translated (word or common sense missing from the dictionary). Hand-edited Thai is never overwritten.

## Sources & licences (TOEIC)
- TOEIC Service List 1.2 and New General Service List 1.2 — Browne, C. & Culligan, B., newgeneralservicelist.com, CC BY-SA 4.0. The TOEIC `meaning` column comes from these lists; `toeic_vocab.csv` is shared under the same licence.
- This product is created by the adaptation of LEXiTRON developed by NECTEC (http://www.nectec.or.th/). (Thai meanings)
- Pronunciation: CMU Pronouncing Dictionary (converted to IPA, US English).
